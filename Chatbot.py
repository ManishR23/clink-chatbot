from flask import Flask, request, jsonify, render_template, session
from openai import OpenAI
import os
from dotenv import load_dotenv

import math
import re

from datetime import timedelta
import uuid

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
            if quantity > item["available"]:
                return None

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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.permanent_session_lifetime = timedelta(days=1)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


SYSTEM_PROMPT = f"""
You are ClinkBot, a helpful, efficient assistant built to help customers estimate and purchase construction materials from Clink.

Your job:
1. Estimate how many units the customer needs based on their project (if they don’t already give you the quantity).
2. Help them choose the right material category (brick, tile, sheet, wood, etc.) based on their build.
3. Narrow options by hole count, color, and use case.
4. Recommend a specific item from Clink’s inventory if we have enough.
5. Compare the price to Home Depot if available.
6. Add a ~10% buffer and round to the nearest 5 units.
7. Be brief, clear, and user-friendly.

---

Clink’s Current Inventory:
{[
  f"{item['name']} ({item['category']}, {item['color']}, {item['color_id']}, {item['num_holes']}): "
  f"Clink = ${item['price_clink']}, "
  f"Home Depot = ${item['price_home_depot']}, "
  f"{item['available']} available"
  for item in inventory_data
]}

---

❗ Guidelines:

- **Don’t assume the material** is brick just because Clink sells it. First ask what they’re building (e.g., wall, bench, patio).
  - Then ask if they prefer brick, wood, concrete, tile, metal, etc.
  - Only proceed once you've clarified the best material category.

- **Face area rules**:
  - For **bricks**, use *length × height* for wall-facing applications.
  - For **tile/sheet/panel/paver**, use *length × width*.

- If the user **gives you a quantity**, trust their number. Don’t ask for dimensions unless they ask you to estimate it.
  - If they provide **both dimensions and quantity**, use their quantity.

- Always **recommend a product title and color** — don’t make the user browse.

- Add a **buffer of 10%** and round up to the **nearest 5**. Call this the “Recommended Quantity”.

- If Clink **doesn’t have enough inventory** for the required amount:
  - Suggest a similar color/item **with enough stock**, if available.
  - If no alternatives are in stock, tell them they’ll have to look elsewhere — but still show how much they’d save if they bought what we *do* have.

- NEVER:
  - Suggest going to Lowe’s or another competitor.
  - Present savings unless we have enough inventory to fulfill that quantity.

---

When to Trigger Cost Calculation:

If you have recommended a specific material **and** you know how many units are needed, you **must always** insert this tag at the end of your message (without explaining it):

[calculate_cost(name="Material Name", quantity=##)]

Use the exact material name as shown in inventory. This allows the system to calculate pricing and savings for the customer.

Even if the customer doesn’t explicitly ask for cost, once the material and quantity are clear, this tag **must** be included.

---

IMPORTANT OVERRIDE:
If the user directly says how many bricks they want (e.g. "I want 80 bricks"), then SKIP all clarification questions about what they’re building, what material type they want, or what use case they have.

Instead, do this:
- Immediately acknowledge the quantity.
- Ask ONLY for their preferred color (if not given).
- Then check our inventory for a matching product.
- If we have a match, recommend the full product title with the hidden cost tag:  
  [calculate_cost(name="...", quantity=##)]

Only ask what they’re building if they have NOT given you a quantity yet.


Tone:
- Friendly, fast, and professional.
- Keep it brief. Avoid long-winded answers.
- Always sound confident and helpful.
"""



@app.route("/")
def home():
    return render_template("index.html")

@app.before_request
def ensure_session():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    if "history" not in session:
        session["history"] = []

convo_history = []

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    if not user_input:
        return jsonify({"error": "No input provided"}), 400
    
    history = session["history"]
    history.append({"role": "user", "content": user_input})

    full_message = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=full_message,
        temperature=0.7
    )

    reply = response.choices[0].message.content

    # Check if GPT inserted a cost calculation tag
    match = re.search(r"\[calculate_cost\(name=['\"](.+?)['\"],\s*quantity=(\d+)\)\]", reply)
    if match:
        name = match.group(1)
        quantity = int(match.group(2))
        result = calculate_cost(name, quantity)

        if result:
            natural_reply = (
                f"You will need {result['Requested Quantity']} {result['Material Name']} for your project.\n"
                f"Clink charges ${result['Clink Price']} compared to ${result['Retail Price']} at Home Depot. "
                f"You're saving ${result['Savings']} with Clink!\n\n"
                f"To be safe, we recommend ordering {result['Recommended Quantity']} "
                f"in case of breakage or cuts.\n"
                f"Total cost would be ${result['Recommended Price Clink']} with Clink vs "
                f"${result['Recommended Price Home Depot']} at Home Depot — "
                f"saving you ${result['Recommended Savings']}."
            )
            history.append({"role": "assistant", "content": natural_reply})
            session["history"] = history
            return jsonify({"reply": natural_reply})

        else:
            # Not enough inventory — suggest partial stock or fallback
            for item in inventory_data:
                if item["name"].lower() == name.lower():
                    partial_qty = item["available"]
                    if partial_qty == 0:
                        error_msg = (
                            f"Unfortunately, we don’t have any {item['name']} in stock right now. "
                            f"You’ll have to look elsewhere."
                        )
                    else:
                        partial_price = round(item["price_clink"] * partial_qty, 2)
                        error_msg = (
                            f"We don’t have enough {item['name']} to fulfill your full request, "
                            f"but we do have {partial_qty} in stock.\n"
                            f"You can still get them from Clink for ${partial_price} — and save some compared to retail."
                        )
                    history.append({"role": "assistant", "content": error_msg})
                    session["history"] = history
                    return jsonify({"reply": error_msg})

    # Normal Reply
    history.append({"role": "assistant", "content": reply})
    session["history"] = history
    return jsonify({"reply": reply})



@app.route("/reset", methods=["POST"])
def reset_chat():
    session["history"] = []
    return jsonify({"status": "Conversation reset."})

    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)