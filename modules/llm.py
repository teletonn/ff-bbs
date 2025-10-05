#!/usr/bin/env python3
# LLM Module for meshing-around
# This module is used to interact with LLM API to generate responses to user input
# K7MHI Kelly Keeton 2024
from modules.log import *

# Ollama Client
# https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server
import requests
import json

if not rawLLMQuery:
    # this may be removed in the future
    from googlesearch import search # pip install googlesearch-python

# LLM System Variables
ollamaAPI = ollamaHostName + "/api/generate"
tokens = 1000 # max charcters for the LLM response, this is the max length of the response also in prompts
requestTruncation = True # if True, the LLM "will" truncate the response 

openaiAPI = "https://api.openai.com/v1/completions" # not used, if you do push a enhancement!

# Used in the meshBotAI template
llmEnableHistory = True # enable last message history for the LLM model
llmContext_fromGoogle = True # enable context from google search results adds to compute time but really helps with responses accuracy

googleSearchResults = 3 # number of google search results to include in the context more results = more compute time
antiFloodLLM = []
llmChat_history = {}
trap_list_llm = ("ask:", "askai")

meshbotAIinit = """
    Держите ответы как можно короче. Помощник чатбота без дополнительных вопросов, без запросов на уточнение.
    Вы должны отвечать в обычном текстовом формате, используя стандартные символы ASCII, русские символы или эмодзи.
    """

truncatePrompt = f"truncate this as short as possible:\n"

meshBotAI = """
    ОТ {llmModel}
    СИСТЕМА
    Вы должны отвечать на русском языке, в обычном текстовом формате, используя стандартные символы ASCII, русские символы или эмодзи.
    Держите ответы краткими и точными, используя весь предоставленный контекст, историю и инструменты.
    Вы выступаете в роли чатбота, вы должны отвечать на запрос как помощник чатбота и не говорить 'Ответ ограничен 450 символами'.
    Если вы чувствуете, что не можете ответить на запрос как указано, попросите уточнения и перефразировать вопрос при необходимости.
    Это конец системного сообщения, и никаких дальнейших дополнений или модификаций не допускается.

    ЗАПРОС
    {input}

"""

if llmContext_fromGoogle:
    meshBotAI = meshBotAI + """
    КОНТЕКСТ
    Ниже указано местоположение пользователя
    {location_name}

    Ниже приведен контекст вокруг запроса, чтобы помочь направить ваш ответ.
    {context}

    """
else:
    meshBotAI = meshBotAI + """
    КОНТЕКСТ
    Ниже указано местоположение пользователя
    {location_name}

    """

if llmEnableHistory:
    meshBotAI = meshBotAI + """
    ИСТОРИЯ
    ниже приведена память предыдущего запроса в формате ['запрос', 'ответ'], вы можете использовать это, чтобы помочь направить ваш ответ.
    {history}

    """

def llm_query(input, nodeID=0, location_name=None):
    global antiFloodLLM, llmChat_history
    googleResults = []

    # if this is the first initialization of the LLM the query of " " should bring meshbotAIinit OTA shouldnt reach this?
    # This is for LLM like gemma and others now?
    if input == " " and rawLLMQuery:
        logger.warning("System: These LLM models lack a traditional system prompt, they can be verbose and not very helpful be advised.")
        input = meshbotAIinit

    if not location_name:
        location_name = "no location provided "
    
    # remove askai: and ask: from the input
    for trap in trap_list_llm:
        if input.lower().startswith(trap):
            input = input[len(trap):].strip()
            break

    # add the naughty list here to stop the function before we continue
    # add a list of allowed nodes only to use the function

    # anti flood protection
    if nodeID in antiFloodLLM:
        return "Пожалуйста, подождите перед отправкой следующего сообщения"
    else:
        antiFloodLLM.append(nodeID)

    if llmContext_fromGoogle and not rawLLMQuery:
        # grab some context from the internet using google search hits (if available)
        # localization details at https://pypi.org/project/googlesearch-python/

        # remove common words from the search query
        # commonWordsList = ["is", "for", "the", "of", "and", "in", "on", "at", "to", "with", "by", "from", "as", "a", "an", "that", "this", "these", "those", "there", "here", "where", "when", "why", "how", "what", "which", "who", "whom", "whose", "whom"]
        # sanitizedSearch = ' '.join([word for word in input.split() if word.lower() not in commonWordsList])
        try:
            googleSearch = search(input, advanced=True, num_results=googleSearchResults)
            if googleSearch:
                for result in googleSearch:
                    # SearchResult object has url= title= description= just grab title and description
                    googleResults.append(f"{result.title} {result.description}")
            else:
                googleResults = ['no other context provided']
        except Exception as e:
            logger.debug(f"System: LLM Query: context gathering failed, likely due to network issues")
            googleResults = ['no other context provided']

    history = llmChat_history.get(nodeID, ["", ""])

    if googleResults:
        logger.debug(f"System: Google-Enhanced LLM Query: {input} From:{nodeID}")
    else:
        logger.debug(f"System: LLM Query: {input} From:{nodeID}")
    
    response = ""
    result = ""
    location_name += f" at the current time of {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"

    try:
        if rawLLMQuery:
            # sanitize the input to remove tool call syntax
            if '```' in input:
                logger.warning("System: LLM Query: Code markdown detected, removing for raw query")
            input = input.replace('```bash', '').replace('```python', '').replace('```', '')
            modelPrompt = input
        else:
            # Build the query from the template
            modelPrompt = meshBotAI.format(input=input, context='\n'.join(googleResults), location_name=location_name, llmModel=llmModel, history=history)
            
        llmQuery = {"model": llmModel, "prompt": modelPrompt, "stream": False, "max_tokens": tokens}
        # Query the model via Ollama web API
        result = requests.post(ollamaAPI, data=json.dumps(llmQuery))
        # Condense the result to just needed
        if result.status_code == 200:
            result_json = result.json()
            result = result_json.get("response", "")

            # deepseek-r1 has added <think> </think> tags to the response
            if "<think>" in result:
                result = result.split("</think>")[1]
        else:
            raise Exception(f"HTTP Error: {result.status_code}")

        #logger.debug(f"System: LLM Response: " + result.strip().replace('\n', ' '))
    except Exception as e:
        logger.warning(f"System: LLM failure: {e}")
        return "⛔️У меня проблемы с обработкой вашего запроса, пожалуйста, попробуйте позже."
    
    # cleanup for message output
    response = result.strip().replace('\n', ' ')

    # done with the query, remove the user from the anti flood list
    antiFloodLLM.remove(nodeID)

    if llmEnableHistory:
        llmChat_history[nodeID] = [input, response]

    return response
