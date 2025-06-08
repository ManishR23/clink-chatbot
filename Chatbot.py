from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os
from dotenv import load_dotenv

import math
import re

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

# calculate the cost function
def calculate_cost(name, quantity):
    for item in inventory_data:
        if item["name"].lower() == name.lower():
            clink_price = item["price_clink"] * quantity
            retail_price = item["price_home_depot"] * quantity if item["price_home_depot"] else None
            savings = retail_price - clink_price if retail_price else None

            rec_quantity = int(math.ceil(quantity * 1.1 / 5.0) * 5)
            rec_clink_price = item["price_clink"] * rec_quantity
            rec_home_price = item["price_home_depot"] * rec_quantity if item["price_home_depot"] else None
            rec_savings = rec_home_price - rec_clink_price if rec_home_price else None

            return {
                "Material Name": name,
                "Requested Quantity": quantity,
                "Clink Price": round(clink_price, 2),
                "Retail Price": round(retail_price, 2) if retail_price else "N/A",
                "Savings": round(savings, 2) if savings else "N/A",

                "Recommended Quantity": rec_quantity,
                "Recommended Price Clink": round(rec_clink_price, 2),
                "Recommended Price Home Depot": round(rec_home_price, 2) if rec_home_price else "N/A",
                "Recommended Savings": round(rec_savings, 2) if rec_savings else "N/A"
            }
    return None
    





# Chatbot response
load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


SYSTEM_PROMPT = f"""
You are ClinkBot, a helpful assistant for estimating materials for construction projects.

Here is Clink's current inventory:
{[
  f"{item['name']} ({item['category']}, {item['color']}, {item['color_id']}, {item['num_holes']}): "
  f"Clink = ${item['price_clink']}, "
  f"Home Depot = ${item['price_home_depot']}, "
  f"{item['available']} available"
  for item in inventory_data
]}

Each brick is 9.5in x 2.5in x 2.75in unless otherwise noted.

Your job:
1. Estimate how many units the user needs based on their project.
2. Recommend a color that Clink currently has in stock.
3. Compare prices with Home Depot.
4. If Clink doesn’t have enough, explain how many the user will need to get elsewhere.
5. Respond clearly, kindly, and helpfully.

General guidance:
- Keep responses short and simple — we want the experience to feel easy and frictionless.
- Don’t assume bricks are the right material just because it’s what we carry. If the user mentions building something like a bench, first ask whether they’d prefer wood, brick, metal, etc.
- Never hallucinate. If you don’t know the answer, say so. For example, if the user asks for Lowe’s pricing and we don’t have it, respond with: “I’m not sure about Lowe’s, but here’s what Home Depot charges.”
- Before doing *any* calculations, help the user narrow down what they want: material type, color, and hole count (e.g., 3 vs 4 vs 5). Once narrowed, ask which of those they prefer — make the process methodical and helpful.
- Always mention the product name and color when making a recommendation.

Cost calculations:
- If the user’s request requires a cost calculation, insert this hidden tag somewhere in your reply (don’t explain it):  
  [calculate_cost(name="Material Name", quantity=##)]

- Before giving a final price:
  - First, check how many bricks we have in stock for that specific color.
  - If the requested quantity is **greater than what we have**, do **not** present a savings comparison.
  - Instead, do one of the following:
    1. Suggest a different color or product that has enough stock.
    2. If no alternatives exist, offer to sell them the full quantity we do have and suggest sourcing the rest elsewhere.

- When presenting price and savings:
  - Ease into it conversationally. Say things like:
    “Let me check how many we have first...”
    “Looks like we’ve got enough of that color!”
    “Here’s what that would cost...”
  - Only calculate and present savings if the full quantity is available.

Above all, make the experience feel guided, friendly, and low-effort for the customer. ClinkBot is here to help.

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

    # GPT-cooked regex to find the hidden function call pattern 
    match = re.search(r"\[calculate_cost\(name=['\"](.+?)['\"],\s*quantity=(\d+)\)\]", reply)
    if match:
        name = match.group(1)
        quantity = int(match.group(2))
        result = calculate_cost(name, quantity)

        if result:
            natural_reply = (
                f"You will need {result['Requested Quantity']} {result['Material Name']} for your project."
                f"Clink charges ${result['Clink Price']} compared to ${result['Retail Price']} at Home Depot. "
                f"You're saving ${result['Savings']} with Clink!\n\n"
                f"To be safe, we recommend ordering {result['Recommended Quantity']} "
                f"in case of breakage or cuts.\n"
                f"Total cost would be ${result['Recommended Price Clink']} with Clink vs "
                f"${result['Recommended Price Home Depot']} at Home Depot — "
                f"saving you ${result['Recommended Savings']}."
            )
            convo_history.append({"role": "assistant", "content": natural_reply})
            return jsonify({"reply": natural_reply})

        else:
            error_msg = "Sorry, I couldn’t find that material in our inventory."
            convo_history.append({"role": "assistant", "content": error_msg})
            return jsonify({"reply": error_msg})

    # Normal Response
    convo_history.append({"role": "assistant", "content": reply})

    return jsonify({"reply": reply})


@app.route("/reset", methods=["POST"])
def reset_chat():
    global convo_history
    convo_history = []  # Clear the conversation
    return jsonify({"status": "Conversation reset."})

    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)