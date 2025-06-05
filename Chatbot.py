from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os
from dotenv import load_dotenv

# Inventory of Clink
import csv
def load_inventory():
    inventory = []
    with open("inventory.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["price_clink"] = float(row["price_clink"])
            row["price_home_depot"] = float(row["price_home_depot"]) if row["price_home_depot"] else None
            row["available"] = int(row["available"])
            row["length_in"] = float(row["length_in"]) if row["length_in"] else None
            row["width_in"] = float(row["width_in"]) if row["width_in"] else None
            row["height_in"] = float(row["height_in"]) if row["height_in"] else None
            inventory.append(row)
    return inventory


inventory_data = load_inventory()

# Chatbot response
load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


SYSTEM_PROMPT = f"""
You are ClinkBot, a helpful assistant for estimating materials for construction projects.

Here is Clink's current inventory:
{[
  f"{item['name']} ({item['category']}, {item['color']}): "
  f"Clink = ${item['price_clink']}, "
  f"Home Depot = ${item['price_home_depot']}, "
  f"{item['available']} available"
  for item in inventory_data
]}

Each brick is 9.5in x 2.5in x 2.75in unless otherwise noted.

Your job:
1. Estimate how many units the user needs based on their project
2. Recommend a color Clink has in stock
3. Compare prices with Home Depot and Lowe’s
4. If Clink doesn’t have enough, say how many they’ll need to get elsewhere
5. Respond clearly and kindly

Remember that every time you calculate a price, make sure to show the comparison of Home Depot - its crucial
keep these answers short and sweet please, we want it to be as frictionless for the customer as possible
"""




@app.route("/")
def home():
    return render_template("index.html")

convo_history = []

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    if not user_input:
        return jsonify({"error": "No input provided"}), 400
    
    convo_history.append({"role": "user", "content": user_input})

    full_message = [{"role": "system", "content": SYSTEM_PROMPT}] + convo_history

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=full_message,
        temperature=0.7
    )

    reply = response.choices[0].message.content
    convo_history.append({"role": "assistant", "content": reply})

    return jsonify({"reply": reply})


@app.route("/reset", methods=["POST"])
def reset_chat():
    global conversation_history
    conversation_history = []  # Clear the conversation
    return jsonify({"status": "Conversation reset."})

    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

