from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext import ConversationHandler
import logging
import os
from dotenv import load_dotenv
from llm import load_and_index_pdfs, retrieve_and_generate  # Import LLM-related functions from llm.py

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
    # Get the user's name and the folder path
    user_name = update.message.from_user.full_name

    # Handle case when the folder path has not been set
    if not pdf_folder_path:
        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"No folder path has been set yet. Please set it using the /path_folder command."
        )
    else:
        # List all PDF files in the folder
        if pdf_files_in_folder:
            file_list = "\n".join(pdf_files_in_folder)
            folder_info = f"The folder path is currently set to: {pdf_folder_path}\n\nPDF Files:\n{file_list}"
        else:
            folder_info = f"The folder path is currently set to: {pdf_folder_path}, but no PDF files were found."

        # Respond with the user's name, folder path, and PDF file list (if available)
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
    return ConversationHandler.END


# Ask command handler (legacy, to retain backward compatibility)
async def ask(update: Update, context):
    # Check if the vector store was loaded and if there are PDF files
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

    # Check if the response is valid
    if response == "Invalid folder path.":
        await update.message.reply_text(
            "The vector store is not loaded correctly. Please reset the folder path using /path_folder.")
    else:
        # Handle case where source_files is None
        if source_files:
            reference_message = "\n".join([f"Document: {file}" for file in source_files])
        else:
            reference_message = "No document references found."

        await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")

    return ConversationHandler.END


# Handle all user messages as potential AI questions
async def handle_message(update: Update, context):
    # Check if the folder path and PDFs are ready
    if not vector_store_loaded:
        await update.message.reply_text(
            "The folder path has not been set or PDFs are not indexed. Use /path_folder first.")
        return

    if not pdf_files_in_folder:
        await update.message.reply_text("No PDF documents found in the folder. Please add PDF documents to the folder.")
        return

    # Treat the user's message as a question for the AI
    user_message = update.message.text
    response, source_files = retrieve_and_generate(user_message)

    # Send the response with references to the source documents
    if source_files:
        reference_message = "\n".join([f"Document: {file}" for file in source_files])
    else:
        reference_message = "No document references found."

    await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")


# Main function to set up the bot
def main():
    # Set up the application
    application = ApplicationBuilder().token(telegram_token).build()

    # Conversation handler for /path_folder command
    path_folder_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('path_folder', path_folder)],
        states={
            WAITING_FOR_FOLDER_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_path_folder)],
        },
        fallbacks=[]
    )

    # Conversation handler for /ask command
    ask_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('ask', ask)],
        states={
            WAITING_FOR_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question)],
        },
        fallbacks=[]
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))  # Add the status handler
    application.add_handler(path_folder_conv_handler)
    application.add_handler(ask_conv_handler)

    # Add a handler for all user messages as AI questions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot with polling
    application.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
