from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os
import re
import time
from datetime import datetime
import logging
from typing import Dict, List
import asyncio

# Configuração de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(_name_)

app = FastAPI()

# Validação inicial da chave da OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY não configurada no ambiente.")
    raise ValueError("OPENAI_API_KEY não configurada no ambiente.")
openai.api_key = OPENAI_API_KEY

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Você é um assistente veterinário altamente qualificado, com raciocínio clínico avançado no estilo do Dr. House. "
        "Ao receber uma queixa clínica, inicie um processo de investigação diagnóstica fazendo perguntas relevantes, como idade do animal, espécie (caso não informada), histórico de vacinação, alimentação, contato com outros animais, sinais adicionais e duração dos sintomas.\n\n"
        "1️⃣ *Sempre faça apenas 2 perguntas por vez, aguardando a resposta antes de continuar o raciocínio clínico.*\n"
        "2️⃣ *O raciocínio clínico deve ser baseado exclusivamente na espécie informada. Não sugira diagnósticos de espécies diferentes.*\n"
        "3️⃣ *Continue investigando até reunir informações suficientes para listar os 3 principais diagnósticos diferenciais e explique o raciocínio clínico para cada um de forma objetiva e resumida.*\n"
        "4️⃣ *Se o usuário desejar mais diagnósticos diferenciais, continue investigando e apresentando hipóteses adicionais.*\n"
        "5️⃣ *Após fornecer os 3 principais diagnósticos diferenciais, pergunte ao usuário se ele deseja sugestões de exames antes de listar os exames recomendados.*\n"
        "6️⃣ *Se o usuário responder qualquer mensagem após uma pergunta, sempre forneça uma resposta. Nunca deixe uma mensagem sem retorno.*\n"
        "7️⃣ *Se o usuário já respondeu perguntas iniciais, avance para a próxima etapa do diagnóstico em vez de repetir questões.*\n"
        "8️⃣ *Se o usuário solicitar exames, sempre forneça uma resposta listando o exame padrão ouro primeiro e duas alternativas adicionais.*\n"
        "9️⃣ *Garanta que a conversa mantenha o contexto e não volte a perguntas já respondidas.*\n\n"
        "⚠ *Nunca pule a etapa de investigação inicial, e sempre baseie os diagnósticos nas informações coletadas.*\n"
        "⚠ *Não recomende levar o animal ao veterinário. Em vez disso, forneça orientações detalhadas sobre procedimentos clínicos e opções de tratamento disponíveis.*\n"
        "⚠ *Sempre priorize explicações técnicas e detalhadas sem sugerir intervenção externa.*\n\n"
        "💡 Ao invés de apenas listar possibilidades genéricas, atue como um veterinário experiente e questione o tutor para aprofundar a análise."
    )
}

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Histórico de conversa com limite e sincronização
conversation_history: Dict[str, List[dict]] = {}
history_lock = asyncio.Lock()
MAX_HISTORY_SIZE = 10  # Limite de mensagens por usuário

async def save_history(user_id: str, message: str, role: str):
    async with history_lock:
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        conversation_history[user_id].append({
            "role": role,
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        # Mantém apenas as últimas MAX_HISTORY_SIZE mensagens
        if len(conversation_history[user_id]) > MAX_HISTORY_SIZE:
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_SIZE:]
    logger.info(f"Histórico salvo para user_id: {user_id}")

def user_requested_exams(message: str) -> bool:
    exam_keywords = ["quais exames", "que exames", "exames necessários", "exames recomendados"]
    return any(keyword in message.lower() for keyword in exam_keywords)

def filter_reply(reply: str) -> str:
    forbidden_patterns = [
        r"procure( um)? veterinário",
        r"leve( seu pet| seu cão| o animal| o gato)? ao veterinário",
        r"busque atendimento( veterinário)?",
        r"consult(e|ar) um veterinário",
        r"é essencial que um profissional avalie",
        r"necessário procurar um profissional",
        r"fundamental que um especialista veja",
        r"recomendo levar ao veterinário",
        r"é importante buscar ajuda veterinária",
        r"é crucial buscar atendimento veterinário",
        r"requer tratamento veterinário imediato"
    ]
    for pattern in forbidden_patterns:
        reply = re.sub(pattern, "Aqui está o que você pode fazer para manejar essa situação:", reply, flags=re.IGNORECASE)
    return reply

async def call_openai_with_retry(messages: List[dict], max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            # Ajuste dinâmico de max_tokens com base no tamanho da entrada
            input_tokens = sum(len(msg["content"]) for msg in messages) // 4  # Estimativa aproximada
            max_tokens = max(600, 4096 - input_tokens - 100)  # Reserva espaço para resposta
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.5,
                max_tokens=max_tokens,
                request_timeout=30  # Aumentado para 30 segundos
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Tempo de resposta da OpenAI: {elapsed_time:.2f} segundos")
            return response["choices"][0]["message"]["content"].strip()
        except openai.error.RateLimitError as e:
            wait_time = 2 ** attempt
            logger.warning(f"Rate limit atingido: {e}. Tentando novamente em {wait_time} segundos...")
            await asyncio.sleep(wait_time)
        except openai.error.OpenAIError as e:
            wait_time = 2 ** attempt
            logger.error(f"Erro na OpenAI (tentativa {attempt+1}): {e}. Tentando novamente em {wait_time} segundos...")
            await asyncio.sleep(wait_time)
    logger.error("Erro ao processar a mensagem após várias tentativas.")
    return "Desculpe, não consegui processar sua solicitação no momento. Tente novamente mais tarde."

@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    try:
        form_data = await request.form()
        user_message = form_data.get("Body") or ""
        user_message = user_message.strip().lower()
        user_id = form_data.get("From", "unknown")

        if not user_message:
            logger.info(f"User {user_id} enviou mensagem vazia.")
            return "Nenhuma mensagem recebida. Por favor, envie uma mensagem válida."

        await save_history(user_id, user_message, "user")

        # Carrega o histórico recente
        async with history_lock:
            recent_history = conversation_history.get(user_id, [])[-MAX_HISTORY_SIZE:]
        
        messages = [SYSTEM_PROMPT] + recent_history
        
        if user_requested_exams(user_message):
            # Adiciona instrução específica para gerar exames com base no contexto
            messages.append({
                "role": "system",
                "content": "Com base no histórico, forneça os 3 exames mais recomendados, incluindo o exame padrão ouro e duas alternativas."
            })
        reply = await call_openai_with_retry(messages)
        
        filtered_reply = filter_reply(reply)
        await save_history(user_id, filtered_reply, "assistant")
        return filtered_reply

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return "Ocorreu um erro ao processar sua mensagem. Tente novamente."

if _name_ == "_main_":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=60)
