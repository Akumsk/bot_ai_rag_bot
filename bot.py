from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext import ConversationHandler
import logging
import os
from dotenv import load_dotenv
from llm import load_and_index_pdfs, retrieve_and_generate  # Import LLM-related functions from llm.py
from db import add_user_to_db, get_last_folder  # Import the necessary functions from db.py

# Load environment variables
load_dotenv()

# Set up API keys
telegram_token = os.getenv('TELEGRAM_TOKEN')

# States for ConversationHandler
WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION = range(2)

# Global variables
pdf_folder_path = ""
vector_store_loaded = False  # Track if the vector store was successfully loaded
pdf_files_in_folder = []  # Track the list of PDF files in the folder


# Start command handler
async def start(update: Update, context):
    global pdf_folder_path, vector_store_loaded, pdf_files_in_folder  # Track folder and PDF state

    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name

    # Try to get the last folder from the database for the user
    last_folder = get_last_folder(user_id)

    if last_folder:
        pdf_folder_path = last_folder  # Set the retrieved folder as the current folder
        # Check if the folder contains PDF files
        pdf_files_in_folder = [f for f in os.listdir(pdf_folder_path) if f.endswith(".pdf")]
        if pdf_files_in_folder:
            load_and_index_pdfs(pdf_folder_path)  # Load and index the PDFs
            vector_store_loaded = True  # Mark the vector store as successfully loaded
            await update.message.reply_text(
                f"Welcome back, {user_name}! I have loaded your previous folder for context:\n\n {pdf_folder_path}\n\n"
                f"If you need to change the folder please put /path_folder \n"
                "Also, you can interact with the bot using the following commands:\n"
                "/start - Display this introduction message.\n"
                "/ask - Ask a question about the content of the documents.\n"
                "/status - Display current user and folder path information, along with a list of PDF files in the folder.\n"
                "Additionally, you can send any message without a command, and it will be treated as a question."
            )
        else:
            await update.message.reply_text(
                f"Welcome back, {user_name}! However, no PDF files were found in your last folder: {pdf_folder_path}."
            )
    else:
        await update.message.reply_text(
            "Welcome to the AI document assistant bot! This bot generates text-based responses using documents "
            "in a specified folder. You can interact with the bot using the following commands:\n\n"
            "/start - Display this introduction message.\n"
            "/path_folder - Set the folder path where your PDF documents are located.\n"
            "/ask - Ask a question about the content of the documents.\n"
            "/status - Display current user and folder path information, along with a list of PDF files in the folder.\n"
            "Additionally, you can send any message without a command, and it will be treated as a question."
        )


# Status command handler
async def status(update: Update, context):
    user_name = update.message.from_user.full_name

    if not pdf_folder_path:
        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"No folder path has been set yet. Please set it using the /path_folder command."
        )
    else:
        if pdf_files_in_folder:
            file_list = "\n".join(pdf_files_in_folder)
            folder_info = f"The folder path is currently set to: {pdf_folder_path}\n\nPDF Files:\n{file_list}"
        else:
            folder_info = f"The folder path is currently set to: {pdf_folder_path}, but no PDF files were found."

        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"{folder_info}"
        )


# Path folder command handler
async def path_folder(update: Update, context):
    await update.message.reply_text("Please provide the folder path for your PDFs:")
    return WAITING_FOR_FOLDER_PATH


# Handle receiving the folder path
async def set_path_folder(update: Update, context):
    global pdf_folder_path, vector_store_loaded, pdf_files_in_folder  # Use these to track folder and PDF state

    folder_path = update.message.text
    user_id = update.message.from_user.id  # Get the user ID from Telegram
    user_name = update.message.from_user.full_name  # Get the user name from Telegram

    # Check if the folder path exists
    if not os.path.isdir(folder_path):
        await update.message.reply_text("Invalid folder path. Please provide a valid path.")
        return ConversationHandler.END

    # Check if there are PDF files in the folder
    pdf_files_in_folder = [f for f in os.listdir(folder_path) if f.endswith(".pdf")]
    if not pdf_files_in_folder:
        await update.message.reply_text("No PDF files found in the folder. Please provide a folder containing PDFs.")
        return ConversationHandler.END

    # Set the folder path and process PDFs
    pdf_folder_path = folder_path
    load_and_index_pdfs(pdf_folder_path)  # This loads and indexes the PDF files
    vector_store_loaded = True  # Mark that the vector store is successfully loaded
    await update.message.reply_text(f"Folder path successfully set to: {pdf_folder_path} and PDFs have been indexed.")

    # Call add_user_to_db to save user information in the database
    add_user_to_db(user_id=user_id, user_name=user_name, folder=pdf_folder_path)

    return ConversationHandler.END


# Ask command handler (legacy, to retain backward compatibility)
async def ask(update: Update, context):
    if not vector_store_loaded:
        await update.message.reply_text(
            "The folder path has not been set or PDFs are not indexed. Use /path_folder first.")
        return ConversationHandler.END

    if not pdf_files_in_folder:
        await update.message.reply_text("No PDF documents found in the folder. Please add PDF documents to the folder.")
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
    if not vector_store_loaded:
        await update.message.reply_text(
            "The folder path has not been set or PDFs are not indexed. Use /path_folder first.")
        return

    if not pdf_files_in_folder:
        await update.message.reply_text("No PDF documents found in the folder. Please add PDF documents to the folder.")
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
