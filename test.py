from llm import load_and_index_documents
path=r'E:\Python_Projects\bot_ai_rag_bot\context\docs1'
dacs=load_and_index_documents(path)
print(dacs)