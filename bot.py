from dotenv import load_dotenv
import os
import fitz  # Import PyMuPDF directly
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext import ConversationHandler

from langchain_openai import ChatOpenAI  # Updated import for ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import RetrievalQA

import logging

load_dotenv()

# Set up OpenAI API key
openai_api_key = os.getenv('OPENAI_API_KEY')
telegram_token = os.getenv('TELEGRAM_TOKEN')

# Initialize LLM
llm = ChatOpenAI(openai_api_key=openai_api_key)

# Global variables
pdf_folder_path = ""
vector_store = None

# States for ConversationHandler
WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION = range(2)

# Function to load and process PDF files and create FAISS index
def load_and_index_pdfs(folder_path):
    global vector_store

    # Load and read PDFs from folder
    documents = []
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            file_path = os.path.join(folder_path, filename)
            loader = PyMuPDFLoader(file_path)
            documents.extend(loader.load())

    # Split documents into smaller chunks
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    split_docs = text_splitter.split_documents(documents)

    # Create embeddings using OpenAI embeddings
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)

    # Use FAISS from Langchain to store the document embeddings
    vector_store = FAISS.from_documents(split_docs, embeddings)

# Function to handle retrieving and generating response using RAG
def retrieve_and_generate(prompt: str):
    global vector_store
    if not vector_store:
        return "Please set the folder path using /path_folder and ensure PDFs are loaded."

    # Set up retriever
    retriever = vector_store.as_retriever()

    # Use Langchain's RetrievalQA Chain to get the response
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff"
    )

    # Generate answer based on retrieved documents
    response = qa_chain.run(prompt)
    return response

# Start command handler
async def start(update: Update, context):
    await update.message.reply_text(
        "Welcome to the AI document assistant bot! This bot generates text-based responses using documents "
        "in a specified folder. You can interact with the bot using the following commands:\n\n"
        "/start - Display this introduction message.\n"
        "/path_folder - Set the folder path where your PDF documents are located.\n"
        "/ask - Ask a question about the content of the documents.\n"
    )

# Path folder command handler
async def path_folder(update: Update, context):
    await update.message.reply_text("Please provide the folder path for your PDFs:")
    return WAITING_FOR_FOLDER_PATH  # Wait for next message containing the folder path

# Handle receiving the folder path
async def set_path_folder(update: Update, context):
    global pdf_folder_path
    folder_path = update.message.text

    # Check if the folder path exists
    if not os.path.isdir(folder_path):
        await update.message.reply_text("Invalid folder path. Please provide a valid path.")
        return ConversationHandler.END

    # Check if there are PDF files in the folder
    pdf_files = [f for f in os.listdir(folder_path) if f.endswith(".pdf")]
    if not pdf_files:
        await update.message.reply_text("No PDF files found in the folder. Please provide a folder containing PDFs.")
        return ConversationHandler.END

    # Set the folder path and process PDFs
    pdf_folder_path = folder_path
    load_and_index_pdfs(pdf_folder_path)
    await update.message.reply_text(f"Folder path successfully set to: {pdf_folder_path} and PDFs have been indexed.")
    return ConversationHandler.END

# Ask command handler
async def ask(update: Update, context):
    await update.message.reply_text("Please provide the question you want to ask about the documents:")
    return WAITING_FOR_QUESTION  # Wait for the next message containing the user's question

# Handle receiving the user's question
async def ask_question(update: Update, context):
    user_prompt = update.message.text
    response = retrieve_and_generate(user_prompt)
    await update.message.reply_text(response)
    return ConversationHandler.END  # End the conversation

# Main function to set up the bot
def main():
    # Telegram Bot Token
    token = telegram_token

    # Set up the application
    application = ApplicationBuilder().token(token).build()

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

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(path_folder_conv_handler)
    application.add_handler(ask_conv_handler)

    # Start the bot with polling
    application.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()