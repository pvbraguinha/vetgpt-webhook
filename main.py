from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import openai
import os

app = FastAPI()

# Configurar chave da OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Perguntas frequentes
FAQ = {
    "meu cachorro está vomitando": "O vômito pode ter várias causas, como alimentação inadequada, infecção ou problemas gastrointestinais. Para aliviar, mantenha-o hidratado e ofereça uma dieta leve, como frango cozido e arroz.",
    "meu gato não quer comer": "A falta de apetite pode estar relacionada a estresse, problemas dentários ou doenças. Tente oferecer comida úmida ou aquecer levemente a ração para estimular o paladar.",
    "qual a melhor ração para cães?": "A melhor ração depende do porte, idade e necessidades do seu cão. Marcas premium costumam oferecer melhor qualidade nutricional."
}

# Configuração do prompt
SYSTEM_PROMPT = {
    "role": "system",
    "content": "Você é um assistente veterinário altamente qualificado. Responda com precisão técnica e profissional, fornecendo diagnósticos, tratamentos e orientações detalhadas, como um veterinário faria durante uma consulta presencial. Evite indicar que o tutor procure outro veterinário e forneça a melhor solução possível. Mantenha o contexto da conversa para responder de forma coerente e contínua."
}

# Endpoint de Health Check
@app.get("/")
async def read_root():
    return {"message": "App is alive!"}

# Histórico de conversa para manter o contexto
conversation_history = {}

# Endpoint para o webhook
@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form_data = await request.form()
    user_message = form_data.get("Body", "").strip().lower()
    user_id = form_data.get("From", "unknown")  # Identificador único do usuário
    
    if not user_message:
        return "Nenhuma mensagem recebida."
    
    # Verificar perguntas frequentes
    for pergunta, resposta in FAQ.items():
        if pergunta in user_message:
            return resposta
    
    # Criar fluxo de perguntas interativo
    follow_up_questions = {
        "vomitando": "Ele comeu algo diferente hoje? O vômito tem sangue ou é apenas líquido? Podemos sugerir um tratamento com base nos sintomas.",
        "diarreia": "A diarreia é frequente? O pet está se hidratando bem? Podemos indicar uma abordagem para estabilizar a situação.",
        "não quer comer": "Há quantos dias ele está sem comer? Ele tem apresentado outros sintomas? Dependendo da situação, há algumas técnicas para estimular a alimentação."
    }
    
    for keyword, question in follow_up_questions.items():
        if keyword in user_message:
            return question
    
    # Recuperar histórico da conversa
    if user_id not in conversation_history:
        conversation_history[user_id] = [SYSTEM_PROMPT]
    
    conversation_history[user_id].append({"role": "user", "content": user_message})
    
    # Chamada para a OpenAI mantendo o histórico
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=conversation_history[user_id],
            temperature=0.5,
            max_tokens=200
        )
        reply = response["choices"][0]["message"]["content"].strip()
        conversation_history[user_id].append({"role": "assistant", "content": reply})
    except Exception as e:
        reply = f"Erro ao processar a mensagem: {str(e)}"
    
    return reply

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
