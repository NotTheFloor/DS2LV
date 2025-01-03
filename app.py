from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    Response,
    send_from_directory,
    abort,
    session,
    send_file,
    jsonify,
)
from flask_sse import sse
import dotenv

# import bleach
import os, shutil, threading, uuid, requests, secrets, string, re, time, unicodedata
from datetime import timedelta, datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError

import ds2logreader

dotenv.load_dotenv()

CDB_NAME = "ds2lv-db"
CDB_CONTAINER_NAME = "emails"
CDB_ENDPOINT = os.getenv("COSMOS_ENDPOINT")
CDB_KEY = os.getenv("COSMOS_KEY")
EMAIL_PARTITION_KEY = "Email Addresses"

is_prod = os.getenv("IS_PROD")
file_root = os.getenv("FILE_ROOT")
sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
key_path = PartitionKey(path="/emailId")

UPLOAD_FOLDER = os.path.join("", "uploads")
ARCHIVE_FOLDER = os.path.join(file_root, "archive")
OUTPUT_TEMP_FOLDER = os.path.join("", "output_temp")
FINAL_FOLDER = os.path.join(file_root, "final")

SYS_LOG_FOLDER = os.path.join(file_root, "logs")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

assert app.secret_key is not None

# Add the Redis URL to your application's configuration
# Replace "redis://localhost:6379" with your Redis server's URL if it's not on localhost
app.config["REDIS_URL"] = os.getenv("REDIS_URL")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=4)

app.register_blueprint(sse, url_prefix="/stream")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ARCHIVE_FOLDER"] = ARCHIVE_FOLDER
app.config["OUTPUT_TEMP_FOLDER"] = OUTPUT_TEMP_FOLDER
app.config["FINAL_FOLDER"] = FINAL_FOLDER
app.config["RECAPTCHA_SECRET_KEY"] = os.getenv("RC_SECRET_KEY_V2")


def sys_log(msg, filename="std_out.log"):
    current_datetime = datetime.now()
    formatted_datetime = current_datetime.strftime("%Y/%m/%d %H:%M:%S")
    full_path = os.path.join(SYS_LOG_FOLDER, filename)

    with open(full_path, "a") as file:
        file.write(f"{formatted_datetime} - {msg}\n")


def is_valid_email(email):
    """Check if the given string looks like an email address."""
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None


def generate_random_key(length=32):
    """Generate a random key of given length."""
    characters = string.ascii_letters + string.digits
    return "".join(secrets.choice(characters) for _ in range(length))


def get_cdb_container():
    client = CosmosClient(CDB_ENDPOINT, CDB_KEY)

    database = client.create_database_if_not_exists(id=CDB_NAME)

    return database.create_container_if_not_exists(
        id=CDB_CONTAINER_NAME, partition_key=key_path
    )


def send_email(
    to_email, content, subject, from_email="contact@synlective.com"
):
    # Was causing & to become &amp; breaking Flask routing
    # content = bleach.clean(content)

    # Prepare the email
    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        plain_text_content=content,
    )

    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        sys_log(f"Sent email to {to_email}")
        return jsonify({"message": "Email sent successfully"}), 200
    except Exception as e:
        return (
            jsonify(
                {
                    "message": "An error occurred while sending the email",
                    "error": str(e),
                }
            ),
            500,
        )


@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    feedback = data.get("feedback")

    send_email(
        "contact@synlective.com", feedback, "DS2LV - New feedback received"
    )

    return "Feedback received successfully"


@app.route("/recap", methods=["POST"])
def process_recaptcha():
    if "session_id" not in session:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id

    if is_prod:
        data = request.get_json()
        recaptcha_response = data.get("g-recaptcha-response")
        # recaptcha_response = request.form.get("g-recaptcha-response")

        if recaptcha_response:
            data = {
                "secret": app.config["RECAPTCHA_SECRET_KEY"],
                "response": recaptcha_response,
            }
            google_response = requests.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data=data,
            )
            google_response_json = google_response.json()
            if not google_response_json["success"]:
                print("Invalid reCAPTCHA response")
                return "Invalid reCAPTCHA. Please try again.", 400
        else:
            print("No reCAPTCHA response")
            return "No reCAPTCHA. Please try again.", 400

    session["valid"] = True

    return "", 200


@app.route("/", methods=["GET", "POST"])
def index():
    if "session_id" not in session:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        sys_log(f"[{request.remote_addr}] - {session_id}", "sessions.log")

    if not is_prod:
        session["valid"] = True

    if request.method == "POST":
        if "valid" not in session:
            print("reCaptcha no verified")
            return "reCaptcha no verified", 401

        session_id = session["session_id"]

        # Create a new directory to store this user's files
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
        os.makedirs(upload_dir, exist_ok=True)

        # Similar for the output temp directory
        output_temp_dir = os.path.join(
            app.config["OUTPUT_TEMP_FOLDER"], session_id
        )
        os.makedirs(output_temp_dir, exist_ok=True)

        # Similar for the archive directory
        archive_dir = os.path.join(app.config["ARCHIVE_FOLDER"], session_id)
        os.makedirs(archive_dir, exist_ok=True)

        # Similar for the final directory
        final_dir = os.path.join(app.config["FINAL_FOLDER"], session_id)
        os.makedirs(final_dir, exist_ok=True)

        # Define a regular expression pattern to match unsafe characters
        unsafe_chars_pattern = re.compile(r'[\\/:*?"<>|]')

        total_file_size = 0
        for file in request.files.getlist("file"):
            original_filename = file.filename
            # Move the file cursor to the end to get the file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            total_file_size += file_size

            # Reset the file cursor back to the beginning for saving the file
            file.seek(0)

            if total_file_size > 524288000:
                print(
                    f"ERROR: User attempted to upload {total_file_size} total bytes"
                )
                return "Total files size too large", 401

            if file_size > 157286400:
                print(f"ERROR: User tried to download {file_size} bytes")
                return "Files size too large", 401

            # Normalize the filename
            normalized_filename = (
                unicodedata.normalize("NFKD", original_filename)
                .encode("ascii", "ignore")
                .decode("utf-8")
            )
            # Remove unsafe characters from the filename
            sanitized_filename = re.sub(
                unsafe_chars_pattern, "", normalized_filename
            )
            # Limit the filename length if needed
            sanitized_filename = sanitized_filename[
                :255
            ]  # Example: Limit to 255 characters

            # Save the file with the sanitized filename
            file.save(os.path.join(upload_dir, sanitized_filename))

        return redirect(url_for("index"))

    return render_template("index.html")


def process_files_background(session_id, out_id, settings):
    with app.app_context():
        output_dir = os.path.join(app.config["OUTPUT_TEMP_FOLDER"], session_id)
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
        archive_dir = os.path.join(app.config["ARCHIVE_FOLDER"], session_id)
        final_dir = os.path.join(app.config["FINAL_FOLDER"], session_id)

        group_wot = settings["group_wot"]

        ds2 = ds2logreader.DS2LogReader(
            output_folder=output_dir,
            pedal_threshold=settings["pedal_threshold"],
            mid_pedal_for_wot=settings["min_pedal_for_wot"],
            group_wot=group_wot,
        )

        try:
            for filename in os.listdir(upload_dir):
                if filename[0] == ".":
                    continue

                file_path = os.path.join(upload_dir, filename)
                before_files = ds2logreader.get_unique_files(output_dir)
                result = ds2.process_file(file_path)
                after_files = ds2logreader.get_unique_files(output_dir)
                output_files = list(after_files - before_files)

                if result != "":
                    print(f"Error processing {filename}: {result}")
                    sse.publish(
                        {"message": f"Error processing {filename}: {result}"},
                        type="process_update",
                    )
                    continue

                shutil.move(
                    file_path,
                    os.path.join(archive_dir, filename),
                )

                sse.publish(
                    {
                        "message": f"Processing complete for {filename}",
                        "outputFiles": output_files,
                        "inputFile": filename,
                        "status": "fileComplete",
                    },
                    type="process_update",
                )

            # If empty dir, then no wot runs
            files_processed = ds2logreader.get_unique_files(output_dir)
            files_processed = len(files_processed)
            if files_processed == 0:
                sse.publish(
                    {"message": "No wot runs found", "status": "empty"},
                    type="process_update",
                )
                return out_id

            shutil.make_archive(
                f"{final_dir}/output_{out_id}", "zip", output_dir
            )

            sse.publish(
                {"message": "Processing complete", "status": "complete"},
                type="process_update",
            )

            return out_id
        except Exception as e:
            print(f"Exception: {type(e)}\n{e.args}")
            sse.publish({"message": str(e)}, type="process_update")


@app.route("/process", methods=["POST"])
def process_files():
    session_id = session.get("session_id")
    out_id = str(int(time.time()))
    session["out_id"] = out_id
    settings = request.get_json()["settings"]
    if is_prod:
        process_files_background(session_id, out_id, settings)
    else:
        threading.Thread(
            target=process_files_background,
            args=(
                session_id,
                out_id,
                settings,
            ),
        ).start()
    return Response("Processing started.", 202)


@app.route("/download", methods=["GET"])
def download_file():
    session_id = session["session_id"]
    final_dir = os.path.join(app.config["FINAL_FOLDER"], session_id)
    try:
        sys_log(f"{session_id} downloading output_{session['out_id']}.zip")
        return send_from_directory(
            directory=final_dir,
            path=f"output_{session['out_id']}.zip",
            as_attachment=True,
        )
    except FileNotFoundError:
        sys_log(f"{session_id} file not found error", "errors.log")
        abort(404)


@app.route("/download_page", methods=["GET"])
def download_page():
    email_address = request.args.get("email")
    token = request.args.get("token")

    if email_address and token:
        container = get_cdb_container()

        item = container.read_item(
            item=email_address, partition_key=EMAIL_PARTITION_KEY
        )

        if item["secret"] != token:
            sys_log(f"{email_address} bad secret", "errors.log")
            return "Bad secret", 400

        if not item["is_verified"]:
            sys_log(f"{email_address} not verified", "errors.log")
            return "Email address not verified", 400

        download_url = url_for(
            "retrieve_file",
            email=email_address,
            token=token,
            _external=False,
        )

        return render_template("download.html", download_url=download_url)


@app.route("/retrieve", methods=["GET"])
def retrieve_file():
    email_address = request.args.get("email")
    token = request.args.get("token")

    if email_address and token:
        container = get_cdb_container()

        item = container.read_item(
            item=email_address, partition_key=EMAIL_PARTITION_KEY
        )

        if item["secret"] != token:
            return "Bad secret", 400

        if not item["is_verified"]:
            return "Email address not verified", 400

        item["send_count"] += 1

        container.upsert_item(item)

        try:
            sys_log(
                f"{email_address} downlaoded from email {item['download_link']}"
            )
            return send_file(
                item["download_link"],
                as_attachment=True,
            )
        except FileNotFoundError:
            sys_log(f"{email_address} file not found error", "errors.log")
            abort(404)
    else:
        sys_log(f"Invalid email validation request", "errors.log")
        return "Invalid email validation request", 400


@app.route("/delete-file", methods=["DELETE"])
def delete_file():
    session_id = session["session_id"]
    upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
    data = request.get_json()
    filename = data.get("filename")
    if filename:
        file_path = os.path.join(upload_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return "", 204
        else:
            return "File not found", 404
    else:
        return "Filename not provided", 400


@app.route("/reset", methods=["POST"])
def reset_files():
    session_id = session["session_id"]
    output_dir = os.path.join(app.config["OUTPUT_TEMP_FOLDER"], session_id)

    shutil.rmtree(output_dir)

    return "", 204


@app.route("/email", methods=["POST"])
def email_user():
    session_id = session["session_id"]
    data = request.get_json()
    email_address = data.get("email_address")

    # TODO: Should further validate the email address here
    if not email_address:
        return "No email address found", 400

    if not is_valid_email(email_address):
        return "Email is of an unexpected form", 400

    container = get_cdb_container()

    token = generate_random_key()

    try:
        out_id = session.get("out_id")
        assert out_id

        item = container.read_item(
            item=email_address, partition_key=EMAIL_PARTITION_KEY
        )

        if not item["is_verified"]:
            sys_log(f"{email_address} is not verified", "errors.log")
            return "Email address not verified", 400

        item["secret"] = token
        item["send_count"] += 1

        final_dir = os.path.join(
            app.config["FINAL_FOLDER"], session_id, f"output_{out_id}.zip"
        )

        item["download_link"] = final_dir

        container.upsert_item(item)

        download_url = url_for(
            "download_page",
            email=email_address,
            token=token,
            _external=True,
            _scheme="https",
        )

        content = f"Please click the following link to download your file:\n{download_url}"

        send_email(email_address, content, "DS2LV Download Link")

    except CosmosHttpResponseError as e:
        out_id = session.get("out_id")

        assert out_id

        final_dir = os.path.join(
            app.config["FINAL_FOLDER"], session_id, f"output_{out_id}.zip"
        )

        new_item = {
            "id": email_address,
            "emailId": EMAIL_PARTITION_KEY,
            "secret": token,
            "is_verified": False,
            "retries": 0,
            "send_count": 0,
            "download_link": final_dir,
        }

        container.create_item(new_item)

        validation_url = url_for(
            "validate_email",
            email=email_address,
            token=token,
            _external=True,
            _scheme="https",
        )

        # Send validation email
        content = "This is the first time we're seeing this email address.\n\n"
        content += "Please click the validation link below to validate your email and access your download\n"
        content += "This is a one time step.\n\n"
        content += f"{validation_url}"

        send_email(email_address, content, "DS2LV Email Verification")

        return "", 201

    return "", 200


@app.route("/validate", methods=["GET"])
def validate_email():
    email_address = request.args.get("email")
    token = request.args.get("token")

    if email_address and token:
        container = get_cdb_container()

        item = container.read_item(
            item=email_address, partition_key=EMAIL_PARTITION_KEY
        )

        if item["secret"] != token:
            return "Bad secret", 400

        if item["is_verified"]:
            sys_log(f"{email_address} already verified", "errors.log")
            return "Already verified", 400

        item["is_verified"] = True
        item["send_count"] += 1

        container.upsert_item(item)

        download_url = url_for(
            "download_page",
            email=email_address,
            token=token,
            _external=True,
            _scheme="https",
        )

        content = f"Please click the following link to download your file:\n{download_url}"

        send_email(email_address, content, "DS2LV Download Link")

        return render_template("success.html")
    else:
        return "Invalid email validation request", 400


if __name__ == "__main__":
    app.run(debug=True)
