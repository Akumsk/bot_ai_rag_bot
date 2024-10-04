from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext import ConversationHandler
import logging
import os
from dotenv import load_dotenv
from llm import load_and_index_documents, retrieve_and_generate, evaluate_context_token_count
from db import add_user_to_db, get_last_folder
from settings import project_paths

# Load environment variables
load_dotenv()

# Set up API keys
telegram_token = os.getenv('TELEGRAM_TOKEN')

# States for ConversationHandler
WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION, WAITING_FOR_PROJECT_SELECTION = range(3)

max_tokens = 100000

# Define commands for the menu
async def post_init(application):
    """Post initialization hook for the bot."""
    commands = [
        BotCommand("start", "Display introduction message"),
        BotCommand("folder", "Set folder path for documents"),
        BotCommand("projects", "Select a project from predefined options"),
        BotCommand("ask", "Ask a question about documents"),
        BotCommand("status", "Display current status and information"),
        BotCommand("knowledge_base", "Set context to knowledge base")
    ]
    await application.bot.set_my_commands(commands)

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
        # Check if folder exists and is accessible
        if os.path.isdir(last_folder):
            context.user_data['folder_path'] = last_folder  # Set the retrieved folder as the current folder
            try:
                valid_files_in_folder = [f for f in os.listdir(last_folder) if f.endswith((".pdf", ".docx", ".xlsx"))]
                context.user_data['valid_files_in_folder'] = valid_files_in_folder

                if valid_files_in_folder:
                    try:
                        load_and_index_documents(last_folder)  # Load and index the files
                        context.user_data['vector_store_loaded'] = True
                    except Exception as e:
                        logging.error(f"Error during load_and_index_documents: {e}")
                        await update.message.reply_text(
                            "An error occurred while loading and indexing your documents. Please try again later."
                        )
                        return

                    # Evaluate token count
                    token_count = evaluate_context_token_count(last_folder, max_tokens)
                    percentage_full = (token_count / max_tokens) * 100
                    percentage_full = min(percentage_full, 100)  # Ensure it doesn't exceed 100%

                    await update.message.reply_text(
                        f"Welcome back, {user_name}! I have loaded your previous folder for context:\n\n {last_folder}\n\n"
                        f"Context storage is {percentage_full:.2f}% full.\n\n"
                        f"You can specify any folder by command /folder \n"
                        f"Or select the /projects from predefined options\n"
                        "/start - Display this introduction message.\n"
                        "/ask - Ask a question about the content of the documents.\n"
                        "/status - Display current user and folder path information, along with a list of valid files in the folder.\n"
                        "/knowledge_base - Set the context folder to the knowledge base.\n"
                        "/projects - Select a project folder from predefined options.\n"
                        "Additionally, you can send any message without a command, and it will be treated as a question."
                    )
                else:
                    await update.message.reply_text(
                        f"Welcome back, {user_name}! However, no valid files (PDF, Word, or Excel) were found in your last folder: {last_folder}."
                    )
            except Exception as e:
                logging.error(f"Error accessing folder {last_folder}: {e}")
                await update.message.reply_text(
                    "An error occurred while accessing your last folder. Please select a new context folder."
                )
                return WAITING_FOR_FOLDER_PATH
        else:
            # Folder doesn't exist or is not accessible
            await update.message.reply_text(
                "Your previous folder doesn't exist or you do not have access. Please provide the folder path for your documents (PDF, Word, Excel):"
            )
            return WAITING_FOR_FOLDER_PATH
    else:
        await update.message.reply_text(
            "Welcome to the AI document assistant bot! This bot generates text-based responses using documents "
            "in a specified folder. You can interact with the bot using the following commands:\n\n"
            "/start - Display this introduction message.\n"
            "/folder - Set the folder path where your PDF, Word, or Excel documents are located.\n"
            "/projects - Select a project folder from predefined options.\n"
            "/ask - Ask a question about the content of the documents.\n"
            "/status - Display current user and folder path information, along with a list of valid files in the folder.\n"
            "/knowledge_base - Set the context folder to the knowledge base.\n"
            "Additionally, you can send any message without a command, and it will be treated as a question."
        )

# Projects command handler
async def projects(update: Update, context):
    projects_list = "\n".join([f"{key}" for key in project_paths])
    await update.message.reply_text(f"Please select a project:\n{projects_list}")
    return WAITING_FOR_PROJECT_SELECTION

# Handle project selection
async def handle_project_selection(update: Update, context):
    user_choice = update.message.text.strip()

    folder_path = project_paths.get(user_choice)

    if folder_path:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.full_name

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            await update.message.reply_text("The selected project's folder path does not exist.")
            return ConversationHandler.END

        # Check if there are any valid files (PDF, Word, Excel) in the folder
        valid_files_in_folder = [f for f in os.listdir(folder_path) if f.endswith((".pdf", ".docx", ".xlsx"))]
        if not valid_files_in_folder:
            await update.message.reply_text("No valid files (PDF, Word, or Excel) found in the selected project's folder.")
            return ConversationHandler.END

        # Set user-specific folder path and process the documents
        context.user_data['folder_path'] = folder_path
        context.user_data['valid_files_in_folder'] = valid_files_in_folder
        try:
            load_and_index_documents(folder_path)  # This loads and indexes the documents
            context.user_data['vector_store_loaded'] = True  # Mark that the vector store is successfully loaded
        except Exception as e:
            logging.error(f"Error during load_and_index_documents: {e}")
            await update.message.reply_text(
                "An error occurred while loading and indexing the project documents. Please try again later."
            )
            return ConversationHandler.END

        # Evaluate token count
        token_count = evaluate_context_token_count(folder_path, max_tokens)
        percentage_full = (token_count / max_tokens) * 100
        percentage_full = min(percentage_full, 100)  # Ensure it doesn't exceed 100%

        await update.message.reply_text(
            f"Project folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )

        # Save the user information in the database
        add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)
    else:
        await update.message.reply_text("Invalid selection or project is not available. Please select a valid project number (1 or 2).")
        return ConversationHandler.END

    return ConversationHandler.END

# Status command handler
async def status(update: Update, context):
    user_name = update.message.from_user.full_name
    folder_path = context.user_data.get('folder_path', "")
    valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])

    if not folder_path:
        await update.message.reply_text(
            f"Status Information:\n\n"
            f"Name: {user_name}\n"
            f"No folder path has been set yet. Please set it using the /folder command."
        )
    else:
        if valid_files_in_folder:
            file_list = "\n".join(valid_files_in_folder)
            folder_info = f"The folder path is currently set to: {folder_path}\n\nValid Files (PDF, Word, Excel):\n{file_list}"

            # Evaluate token count
            token_count = evaluate_context_token_count(folder_path, max_tokens)
            percentage_full = (token_count / max_tokens) * 100
            percentage_full = min(percentage_full, 100)  # Ensure it doesn't exceed 100%

            await update.message.reply_text(
                f"Status Information:\n\n"
                f"Name: {user_name}\n"
                f"{folder_info}\n\n"
                f"Context storage is {percentage_full:.2f}% full."
            )
        else:
            folder_info = f"The folder path is currently set to: {folder_path}, but no valid files (PDF, Word, or Excel) were found."
            await update.message.reply_text(
                f"Status Information:\n\n"
                f"Name: {user_name}\n"
                f"{folder_info}"
            )

# Folder command handler
async def folder(update: Update, context):
    await update.message.reply_text("Please provide the folder path for your documents (PDF, Word, Excel):")
    return WAITING_FOR_FOLDER_PATH

# Handle receiving the folder path
async def set_folder(update: Update, context):
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
    try:
        load_and_index_documents(folder_path)  # This loads and indexes the documents
        context.user_data['vector_store_loaded'] = True  # Mark that the vector store is successfully loaded
    except Exception as e:
        logging.error(f"Error during load_and_index_documents: {e}")
        await update.message.reply_text(
            "An error occurred while loading and indexing your documents. Please try again later."
        )
        return ConversationHandler.END

    # Evaluate token count
    token_count = evaluate_context_token_count(folder_path, max_tokens)
    percentage_full = (token_count / max_tokens) * 100
    percentage_full = min(percentage_full, 100)  # Ensure it doesn't exceed 100%

    await update.message.reply_text(
        f"Folder path successfully set to: {folder_path}\n\nValid files have been indexed.\n\n"
        f"Context storage is {percentage_full:.2f}% full."
    )

    # Save the user information in the database
    add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)

    return ConversationHandler.END

# Knowledge base command handler
async def knowledge_base(update: Update, context):
    folder_path = r"G:\Shared drives\NUANU ARCHITECTS\LIB Library\LIB Standards and Regulations"
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name

    # Check if the folder path exists
    if not os.path.isdir(folder_path):
        await update.message.reply_text("The knowledge base folder path does not exist.")
        return

    # Check if there are any valid files (PDF, Word, Excel) in the folder
    valid_files_in_folder = [f for f in os.listdir(folder_path) if f.endswith((".pdf", ".docx", ".xlsx"))]
    if not valid_files_in_folder:
        await update.message.reply_text("No valid files (PDF, Word, or Excel) found in the knowledge base folder.")
        return

    # Set user-specific folder path and process the documents
    context.user_data['folder_path'] = folder_path
    context.user_data['valid_files_in_folder'] = valid_files_in_folder
    try:
        load_and_index_documents(folder_path)  # This loads and indexes the documents
        context.user_data['vector_store_loaded'] = True  # Mark that the vector store is successfully loaded
    except Exception as e:
        logging.error(f"Error during load_and_index_documents: {e}")
        await update.message.reply_text(
            "An error occurred while loading and indexing the knowledge base documents. Please try again later."
        )
        return

    # Evaluate token count
    token_count = evaluate_context_token_count(folder_path, max_tokens)
    percentage_full = (token_count / max_tokens) * 100
    percentage_full = min(percentage_full, 100)  # Ensure it doesn't exceed 100%

    await update.message.reply_text(
        f"Knowledge base folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
        f"Context storage is {percentage_full:.2f}% full."
    )

    # Save the user information in the database
    add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)

# Ask command handler
async def ask(update: Update, context):
    if not context.user_data.get('vector_store_loaded', False):
        await update.message.reply_text(
            "The folder path has not been set or documents are not indexed. Use /folder or /knowledge_base first.")
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
    try:
        response, source_files = retrieve_and_generate(user_prompt)
    except Exception as e:
        logging.error(f"Error during retrieve_and_generate: {e}")
        await update.message.reply_text(
            "An error occurred while processing your question. Please try again later."
        )
        return ConversationHandler.END

    if response == "Invalid folder path.":
        await update.message.reply_text(
            "The vector store is not loaded correctly. Please reset the folder path using /folder or /knowledge_base.")
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
            "The folder path has not been set or documents are not indexed. Use /folder or /knowledge_base first.")
        return

    valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])
    if not valid_files_in_folder:
        await update.message.reply_text("No valid documents (PDF, Word, or Excel) found in the folder. Please add documents to the folder.")
        return

    user_message = update.message.text
    try:
        response, source_files = retrieve_and_generate(user_message)
    except Exception as e:
        logging.error(f"Error during retrieve_and_generate: {e}")
        await update.message.reply_text(
            "An error occurred while processing your message. Please try again later."
        )
        return

    if source_files:
        reference_message = "\n".join([f"Document: {file}" for file in source_files])
    else:
        reference_message = "No document references found."

    await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")

# Error handler
async def error_handler(update: object, context: object) -> None:
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An unexpected error occurred. Please try again later."
        )

# Main function to set up the bot
def main():
    # Build application with the post_init hook
    application = ApplicationBuilder()\
        .token(telegram_token)\
        .post_init(post_init)\
        .build()

    folder_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('folder', folder), CommandHandler('start', start)],
        states={
            WAITING_FOR_FOLDER_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_folder)],
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

    project_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('projects', projects)],
        states={
            WAITING_FOR_PROJECT_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_project_selection)],
        },
        fallbacks=[]
    )

    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("knowledge_base", knowledge_base))
    application.add_handler(folder_conv_handler)
    application.add_handler(ask_conv_handler)
    application.add_handler(project_conv_handler)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
