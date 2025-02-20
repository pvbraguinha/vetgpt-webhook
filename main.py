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
        "2️⃣ **O raciocínio clínico deve ser baseado exclusivamente na espécie informada. Não sugira diagnósticos de espécies diferentes.**\n"
        "3️⃣ **Continue investigando até reunir informações suficientes para listar os 3 principais diagnósticos diferenciais e explique o raciocínio clínico para cada um de forma objetiva e resumida.**\n"
        "4️⃣ **Se o usuário desejar mais diagnósticos diferenciais, continue investigando e apresentando hipóteses adicionais.**\n"
        "5️⃣ **Após fornecer os 3 principais diagnósticos diferenciais, pergunte ao usuário se ele deseja sugestões de exames antes de listar os exames recomendados.**\n"
        "6️⃣ **Se o usuário responder qualquer mensagem após uma pergunta, sempre forneça uma resposta. Nunca deixe uma mensagem sem retorno.**\n"
        "7️⃣ **Se o usuário já respondeu perguntas iniciais, avance para a próxima etapa do diagnóstico em vez de repetir questões.**\n"
        "8️⃣ **Se o usuário solicitar exames, sempre forneça uma resposta listando o exame padrão ouro primeiro e duas alternativas adicionais.**\n"
        "9️⃣ **Garanta que a conversa mantenha o contexto e não volte a perguntas já respondidas.**\n\n"
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

# Função para verificar se o usuário pediu exames
def user_requested_exams(message):
    exam_keywords = ["quais exames", "que exames", "exames necessários", "exames recomendados"]
    return any(keyword in message.lower() for keyword in exam_keywords)

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

# Função para chamada da OpenAI com tentativas de retry e log de tempo
def call_openai_with_retry(messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.5,
                max_tokens=600,  # Aumentado para evitar cortes na resposta
                request_timeout=20  # Tempo máximo de espera para resposta
            )
            elapsed_time = time.time() - start_time
            print(f"Tempo de resposta da OpenAI: {elapsed_time:.2f} segundos")
            return response["choices"][0]["message"]["content"].strip()
        except openai.error.OpenAIError as e:
            wait_time = 2 ** attempt  # Exponencial backoff (2s, 4s, 8s...)
            print(f"Tentativa {attempt+1} falhou: {e}. Tentando novamente em {wait_time} segundos...")
            time.sleep(wait_time)
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
    
    # Se o usuário pedir exames, forçamos a resposta
    if user_requested_exams(user_message):
        reply = "Para confirmar o diagnóstico, os exames recomendados são:\n1️⃣ **Exame padrão ouro:** Exame específico mais confiável para a condição suspeita.\n2️⃣ **Alternativa 1:** Outro exame possível para confirmar a suspeita.\n3️⃣ **Alternativa 2:** Exame complementar para maior precisão."
    else:
        messages = [SYSTEM_PROMPT] + conversation_history[user_id][-10:]
        reply = call_openai_with_retry(messages)
    
    reply = filter_reply(reply)
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=60)
