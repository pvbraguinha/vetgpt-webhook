from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os
import re
import time
from datetime import datetime

app = FastAPI()

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Você é um assistente veterinário altamente qualificado, com um raciocínio clínico avançado no estilo do Dr. House. "
        "Ao receber uma queixa clínica, inicie um processo de investigação diagnóstica fazendo perguntas relevantes, como idade do animal, espécie (caso não tenha sido informada), histórico de vacinação, alimentação, contato com outros animais, sinais adicionais e duração dos sintomas.\n\n"
        "1️⃣ **Sempre faça apenas 2 perguntas por vez, aguardando a resposta antes de continuar o raciocínio clínico.**\n"
        "2️⃣ **Continue investigando até reunir informações suficientes para listar os 3 principais diagnósticos diferenciais e explique o raciocínio clínico para cada um.**\n"
        "3️⃣ **Se o usuário desejar mais diagnósticos diferenciais, continue investigando e apresentando hipóteses adicionais.**\n\n"
        "4️⃣ **Caso o usuário pergunte quais exames realizar, sempre forneça o exame padrão ouro primeiro, informando que ele é considerado o exame mais confiável para aquele diagnóstico, e depois sugira mais duas opções viáveis.**\n\n"
        "⚠ **Nunca pule a etapa de investigação inicial, e sempre baseie os diagnósticos nas informações coletadas.**\n"
        "⚠ **Não recomende levar o animal ao veterinário. Em vez disso, forneça orientações detalhadas sobre os procedimentos clínicos e opções de tratamento disponíveis.**\n"
        "⚠ **Sempre priorize explicações técnicas e detalhadas sem sugerir intervenção externa.**\n\n"
        "💡 Ao invés de apenas listar possibilidades genéricas, atue como um veterinário experiente e questione o tutor para aprofundar a análise."
    )
}

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Histórico de conversa para manter o contexto
conversation_history = {}

# Função para salvar o histórico com timestamp
def save_history(user_id, message, role):
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({
        "role": role,
        "content": message,
        "timestamp": datetime.now().isoformat()
    })

# Função para filtrar recomendações indesejadas
def filter_reply(reply):
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

# Função para chamada da OpenAI com tentativas de retry
def call_openai_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.5,
                max_tokens=600,
                request_timeout=20  # Definindo tempo máximo de espera para resposta
            )
            return response["choices"][0]["message"]["content"].strip()
        except openai.error.OpenAIError as e:
            print(f"Tentativa {attempt+1} falhou: {e}")
            time.sleep(2)  # Espera 2 segundos antes de tentar novamente
    return "Erro ao processar a mensagem após várias tentativas."

# Endpoint para o webhook
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form_data = await request.form()
    user_message = form_data.get("Body", "").strip().lower()
    user_id = form_data.get("From", "unknown")  # Identificador único do usuário
    
    if not user_message:
        return "Nenhuma mensagem recebida."

    # Adicionando a mensagem do usuário ao histórico
    save_history(user_id, user_message, "user")
    
    # Preparação do histórico para a chamada à API do OpenAI
    messages = [SYSTEM_PROMPT] + [msg for msg in conversation_history[user_id] if "content" in msg][-10:]  # Mantém últimas 10 mensagens válidas
    
    reply = call_openai_with_retry(messages)  # Usando função com retry
    
    # Aplicar filtragem para evitar recomendações indesejadas
    reply = filter_reply(reply)
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=30)  # Aumentando tempo de conexão
