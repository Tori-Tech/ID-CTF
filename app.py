from datetime import datetime
import json
from flask import Flask, jsonify, request, render_template
import mysql.connector

app = Flask(__name__)

# There's no password for the SQL database; you can change this if you like
DB_BASE_CONFIG = {
    "host": "localhost",
    "user": "root", 
    "password": "", 
}

#database config
DB_NAME = "id"
DB_CONFIG = {**DB_BASE_CONFIG, "database": DB_NAME}
SEED_FILE = "seed.json"


#this will run at startup unless there is already a populated database and table with this name
def setup_database():
    conn = mysql.connector.connect(**DB_BASE_CONFIG)
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cursor.execute(f"USE {DB_NAME}")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            id_number VARCHAR(255) NOT NULL,
            first_name VARCHAR(255) NOT NULL,
            last_name VARCHAR(255) NOT NULL,
            address VARCHAR(255) NOT NULL,
            date_of_birth DATE NOT NULL
        )
    """)
    print("Table 'users' verified/created successfully.")

    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        try:
            with open(SEED_FILE, "r") as f:
                users_data = json.load(f)

            insert_query = (
                "INSERT INTO users (id, id_number, first_name, last_name, address, date_of_birth) VALUES (%s, %s, %s, %s, %s)"
            )

            data_to_insert = [
                (
                    user["id"],
                    user["id_number"],
                    user["first_name"], 
                    user["last_name"], 
                    user.get("address") or user.get("home_address", ""),
                    user["dob"]
                )
                for user in users_data
            ]

            cursor.executemany(insert_query, data_to_insert)
            conn.commit()
            print(f"Successfully seeded {cursor.rowcount} users into MySQL!")

        except FileNotFoundError:
            print(f"Warning: {SEED_FILE} not found. Skipping seeding step.")
    else:
        print("Table already contains data. Skipping seeding.")

    cursor.close()
    conn.close()


#this function calculates the age of a user
def calculate_age(dob):
    if isinstance(dob, str):
        date_of_birth = datetime.strptime(dob, "%Y-%m-%d").date()
    else:
        date_of_birth = dob

    today = datetime.today().date()
    return (
        today.year
        - date_of_birth.year
        - (
            (today.month, today.day)
            < (date_of_birth.month, date_of_birth.day)
        )
    )


@app.route("/", methods=["GET"])
def home():
    #the login page that you will see
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>OnlyBlogs Login</title>
         <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <h2>Login To OnlyBlogs (18+)</h2>
        <form autocomplete="off" id="verifyForm">
            <div><label>First Name:</label><br><input type="text" id="firstName" name="first_name"></div>
            <div><label>Last Name:</label><br><input type="text" id="lastName" name="last_name"></div>
            <button type="submit">Check Database</button>
        </form>
        <div id="result"></div>

        <script>
            document.getElementById('verifyForm').onsubmit = async (e) => {
                e.preventDefault();
                const resDiv = document.getElementById('result');
                resDiv.innerText = "Checking...";
                
                const response = await fetch('/verify-age', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        first_name: document.getElementById('firstName').value,
                        last_name: document.getElementById('lastName').value
                    })
                });
                
                const data = await response.json();
                if (response.ok) {
                    if (data.over_18) {
                        resDiv.style.color = "green";
                        resDiv.innerText = "Access Granted: User is 18+";
                        setTimeout(() => { window.location.href = `/dashboard?id=${data.user_id}`; }, 1500);
                    } else {
                        resDiv.style.color = "orange";
                        resDiv.innerHTML = `
                            <div>Access Denied: User is Under 18</div>
                            <button class="id-btn" onclick="window.location.href='/submit-id?id=${data.user_id}'">Submit Your ID</button>
                        `;
                    }
                } else {
                    resDiv.style.color = "red";
                    resDiv.innerText = data.details || data.message || "An error occurred";
                }
            };
        </script>
    </body>
    </html>
    """


@app.route("/submit-id", methods=["GET"])
def submit_id():
    # redirect to upload IDs
    user_id = request.args.get("id", "")
    return render_template("upload.html", user_id=user_id)  
   


@app.route("/verify-age", methods=["POST"])
def verify_age():
    data = request.json or {}
    
    first = data.get("first_name", "")
    last = data.get("last_name", "")
    name_query = f"{first} {last}".strip()

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # SQL Injection vulnerability here
        query = f"SELECT date_of_birth, id FROM users WHERE CONCAT(first_name, ' ', last_name) = '{name_query}'"

        cursor.execute(query)
        result = cursor.fetchone()

        if result:
            dob = result[0] 
            user_database_id = result[1]
            is_over_18 = calculate_age(dob) >= 18
            return jsonify({"status": "success", "over_18": is_over_18, "user_id": user_database_id})
        else:
            return jsonify({"status": "error", "message": "User not found"}), 404

    except mysql.connector.Error as e:
        return (
            jsonify({"status": "database_error", "details": str(e)}),
            500,
        )
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()


#this part handles verifying the "ID". It's all done automatically, no actual paperwork required.

@app.route("/bypass-age", methods=["POST"])
def bypass_age():
    data = request.json or {}
    target_id = data.get("user_id")
    
    if not target_id:
        return jsonify({"status": "error", "message": "Missing user identification context"}), 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = "UPDATE users SET date_of_birth = '2000-01-01' WHERE id = %s"
        cursor.execute(query, (target_id,))
        conn.commit()

        return jsonify({
            "status": "success", 
            "message": "ID verified automatically! Your system profile age has been modified to 18+."
        }), 200

    except mysql.connector.Error as e:
        return jsonify({"status": "database_error", "details": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

#handles redirection to a dashboard with an IDOR vulnerability

@app.route("/dashboard", methods=["GET"])
def dashboard():
    #this here can be hacked because the application reads the 'id' parameter directly from the URL string
    user_id = request.args.get("id")
    
    if not user_id:
        return "Missing user ID parameter (?id=)", 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True) 
        query = "SELECT id, first_name, last_name, date_of_birth, id_number FROM users WHERE id = %s"
        cursor.execute(query, (user_id,))
        user_record = cursor.fetchone()

        if user_record:
            # this will check the ID of the user's profile; the administrator account (ID = 1) has a flag
            is_target_profile = (user_record["first_name"] == "Administrator" and user_record["last_name"] == "Of_This_Site")
            
            return render_template(
                "dashboard.html", 
                user=user_record, 
                show_flag=is_target_profile
            )
        
        else:
            return "User account not found.", 404

    except mysql.connector.Error as e:
       return jsonify({"status": "database_error", "details": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    setup_database()
    app.run(port=5000, debug=True)
