from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext import ConversationHandler
import logging
import os
from dotenv import load_dotenv
from llm import load_and_index_documents, retrieve_and_generate  # Import LLM-related functions from llm.py
from db import add_user_to_db, get_last_folder  # Import the necessary functions from db.py

# Load environment variables
load_dotenv()

# Set up API keys
telegram_token = os.getenv('TELEGRAM_TOKEN')

# States for ConversationHandler
WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION = range(2)

# Start command handler
async def start(update: Update, context):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name

    # Initialize user-specific data in context.user_data
    context.user_data['folder_path'] = ""
    context.user_data['vector_store_loaded'] = False
    context.user_data['valid_files_in_folder'] = []

    # Try to get the last folder from the database for the user
    last_folder = get_last_folder(user_id)

    if last_folder:
        context.user_data['folder_path'] = last_folder  # Set the retrieved folder as the current folder
        # Check if the folder contains any valid files (PDF, Word, Excel)
        valid_files_in_folder = [f for f in os.listdir(last_folder) if f.endswith((".pdf", ".docx", ".xlsx"))]
        context.user_data['valid_files_in_folder'] = valid_files_in_folder

        if valid_files_in_folder:
            load_and_index_documents(last_folder)  # Load and index the files
            context.user_data['vector_store_loaded'] = True  # Mark the vector store as successfully loaded
            await update.message.reply_text(
                f"Welcome back, {user_name}! I have loaded your previous folder for context:\n\n {last_folder}\n\n"
                f"If you need to change the folder, please use /path_folder.\n"
                "You can interact with the bot using the following commands:\n"
                "/start - Display this introduction message.\n"
                "/ask - Ask a question about the content of the documents.\n"
                "/status - Display current user and folder path information, along with a list of valid files in the folder.\n"
                "Additionally, you can send any message without a command, and it will be treated as a question."
            )
        else:
            await update.message.reply_text(
                f"Welcome back, {user_name}! However, no valid files (PDF, Word, or Excel) were found in your last folder: {last_folder}."
            )
    else:
        await update.message.reply_text(
            "Welcome to the AI document assistant bot! This bot generates text-based responses using documents "
            "in a specified folder. You can interact with the bot using the following commands:\n\n"
            "/start - Display this introduction message.\n"
            "/path_folder - Set the folder path where your PDF, Word, or Excel documents are located.\n"
            "/ask - Ask a question about the content of the documents.\n"
            "/status - Display current user and folder path information, along with a list of valid files in the folder.\n"
            "Additionally, you can send any message without a command, and it will be treated as a question."
        )

# Status command handler
async def status(update: Update, context):
    user_name = update.message.from_user.full_name

    folder_path = context.user_data.get('folder_path', "")
    valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])

    if not folder_path:
        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"No folder path has been set yet. Please set it using the /path_folder command."
        )
    else:
        if valid_files_in_folder:
            file_list = "\n".join(valid_files_in_folder)
            folder_info = f"The folder path is currently set to: {folder_path}\n\nValid Files (PDF, Word, Excel):\n{file_list}"
        else:
            folder_info = f"The folder path is currently set to: {folder_path}, but no valid files (PDF, Word, or Excel) were found."

        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"{folder_info}"
        )

# Path folder command handler
async def path_folder(update: Update, context):
    await update.message.reply_text("Please provide the folder path for your documents (PDF, Word, Excel):")
    return WAITING_FOR_FOLDER_PATH

# Handle receiving the folder path
async def set_path_folder(update: Update, context):
    folder_path = update.message.text
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name

    # Check if the folder path exists
    if not os.path.isdir(folder_path):
        await update.message.reply_text("Invalid folder path. Please provide a valid path.")
        return ConversationHandler.END

    # Check if there are any valid files (PDF, Word, Excel) in the folder
    valid_files_in_folder = [f for f in os.listdir(folder_path) if f.endswith((".pdf", ".docx", ".xlsx"))]
    if not valid_files_in_folder:
        await update.message.reply_text("No valid files (PDF, Word, or Excel) found in the folder. Please provide a folder containing valid documents.")
        return ConversationHandler.END

    # Set user-specific folder path and process the documents
    context.user_data['folder_path'] = folder_path
    context.user_data['valid_files_in_folder'] = valid_files_in_folder
    load_and_index_documents(folder_path)  # This loads and indexes the documents
    context.user_data['vector_store_loaded'] = True  # Mark that the vector store is successfully loaded
    await update.message.reply_text(f"Folder path successfully set to: {folder_path} and valid files have been indexed.")

    # Save the user information in the database
    add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)

    return ConversationHandler.END

# Ask command handler
async def ask(update: Update, context):
    if not context.user_data.get('vector_store_loaded', False):
        await update.message.reply_text(
            "The folder path has not been set or documents are not indexed. Use /path_folder first.")
        return ConversationHandler.END

    valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])
    if not valid_files_in_folder:
        await update.message.reply_text("No valid documents (PDF, Word, or Excel) found in the folder. Please add documents to the folder.")
        return ConversationHandler.END

    await update.message.reply_text("Please provide the question you want to ask about the documents:")
    return WAITING_FOR_QUESTION

# Handle receiving the user's question and provide document reference
async def ask_question(update: Update, context):
    user_prompt = update.message.text
    response, source_files = retrieve_and_generate(user_prompt)

    if response == "Invalid folder path.":
        await update.message.reply_text(
            "The vector store is not loaded correctly. Please reset the folder path using /path_folder.")
    else:
        if source_files:
            reference_message = "\n".join([f"Document: {file}" for file in source_files])
        else:
            reference_message = "No document references found."

        await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")

    return ConversationHandler.END

# Handle all user messages as potential AI questions
async def handle_message(update: Update, context):
    if not context.user_data.get('vector_store_loaded', False):
        await update.message.reply_text(
            "The folder path has not been set or documents are not indexed. Use /path_folder first.")
        return

    valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])
    if not valid_files_in_folder:
        await update.message.reply_text("No valid documents (PDF, Word, or Excel) found in the folder. Please add documents to the folder.")
        return

    user_message = update.message.text
    response, source_files = retrieve_and_generate(user_message)

    if source_files:
        reference_message = "\n".join([f"Document: {file}" for file in source_files])
    else:
        reference_message = "No document references found."

    await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")

# Main function to set up the bot
def main():
    application = ApplicationBuilder().token(telegram_token).build()

    path_folder_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('path_folder', path_folder)],
        states={
            WAITING_FOR_FOLDER_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_path_folder)],
        },
        fallbacks=[]
    )

    ask_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ask', ask)],
        states={
            WAITING_FOR_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        },
        fallbacks=[]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))  # Add the status handler
    application.add_handler(path_folder_conv_handler)
    application.add_handler(ask_conv_handler)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()