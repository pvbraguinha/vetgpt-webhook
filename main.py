from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os
import re
from datetime import datetime

app = FastAPI()

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": "Você é um assistente veterinário altamente qualificado. Responda com precisão técnica e profissional, fornecendo diagnósticos, tratamentos e orientações detalhadas, como um veterinário faria durante uma consulta presencial. Não recomende que o tutor procure um veterinário ou busque atendimento externo. Seu objetivo é fornecer a melhor orientação possível baseada nos sintomas relatados. Caso seja necessário enfatizar a gravidade da situação, forneça instruções claras sobre primeiros socorros e manejos emergenciais que podem ser feitos em casa antes de qualquer outra recomendação. Mantenha o contexto da conversa para responder de forma coerente e contínua, evitando repetir perguntas desnecessárias. Interprete as perguntas do usuário como um veterinário faria, analisando sintomas, possíveis causas e sugerindo tratamentos adequados."
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
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.5,
            max_tokens=300  # Aumentado para permitir respostas mais detalhadas
        )
        reply = response["choices"][0]["message"]["content"].strip()
        save_history(user_id, reply, "assistant")
        
        # Remover qualquer sugestão de procurar um veterinário usando regex
        forbidden_phrases = ["procure um veterinário", "levar ao veterinário", "busque atendimento veterinário", "consultar um veterinário"]
        for phrase in forbidden_phrases:
            reply = re.sub(rf"\b{phrase}\b", "Aqui está a melhor abordagem para lidar com essa situação:", reply, flags=re.IGNORECASE)

    except Exception as e:
        reply = f"Erro ao processar a mensagem: {str(e)}"
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)

