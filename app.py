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
)

print("Confirming change")
from flask_sse import sse
import dotenv
import os, shutil, threading, uuid

import ds2logreader

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

assert app.secret_key is not None

# Add the Redis URL to your application's configuration
# Replace "redis://localhost:6379" with your Redis server's URL if it's not on localhost
app.config["REDIS_URL"] = os.getenv("REDIS_URL")

# is_prod = os.getenv("IS_PROD")


app.register_blueprint(sse, url_prefix="/stream")

file_root = os.getenv("FILE_ROOT")

UPLOAD_FOLDER = os.path.join(file_root, "uploads")
ARCHIVE_FOLDER = os.path.join(file_root, "archive")
OUTPUT_TEMP_FOLDER = os.path.join(file_root, "output_temp")
FINAL_FOLDER = os.path.join(file_root, "final")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ARCHIVE_FOLDER"] = ARCHIVE_FOLDER
app.config["OUTPUT_TEMP_FOLDER"] = OUTPUT_TEMP_FOLDER
app.config["FINAL_FOLDER"] = FINAL_FOLDER


@app.before_request
def create_session():
    # Check if session is not initialized
    if "session_id" not in session:
        # Generate a unique id for the session
        session_id = str(uuid.uuid4())
        # Save the session id in flask's session
        session["session_id"] = session_id
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


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        session_id = session["session_id"]
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
        for file in request.files.getlist("file"):
            filename = file.filename
            file.save(os.path.join(upload_dir, filename))
        return redirect(url_for("index"))

    return render_template("index.html")


def process_files_background(session_id):
    with app.app_context():
        output_dir = os.path.join(app.config["OUTPUT_TEMP_FOLDER"], session_id)
        upload_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
        archive_dir = os.path.join(app.config["ARCHIVE_FOLDER"], session_id)
        final_dir = os.path.join(app.config["FINAL_FOLDER"], session_id)
        ds2 = ds2logreader.DS2LogReader(
            output_folder=output_dir, auto_run=False
        )
        try:
            for filename in os.listdir(upload_dir):
                if filename[0] == ".":
                    print(f"Skipping file {filename}")
                    continue

                file_path = os.path.join(upload_dir, filename)
                print(f"Processing file {file_path}")
                before_files = ds2logreader.get_unique_files(output_dir)
                result = ds2.process_file(file_path)
                after_files = ds2logreader.get_unique_files(output_dir)
                print("Done processing file. Result: '" + result + "'")
                output_files = list(after_files - before_files)

                if result != "":
                    sse.publish(
                        {"message": f"Error processing {filename}: {result}"},
                        type="process_update",
                    )
                    continue

                print("Moving file")
                shutil.move(
                    file_path,
                    os.path.join(archive_dir, filename),
                )
                # Assuming process_file method generates output in OUTPUT_TEMP_FOLDER
                print("File moved")

                sse.publish(
                    {
                        "message": f"Processing complete for {filename}",
                        "outputFiles": output_files,
                        "status": "fileComplete",
                    },
                    type="process_update",
                )

            print("Making archive")
            shutil.make_archive(f"{final_dir}/output", "zip", output_dir)
            print("Archive made")

            # # Delete the output_temp directory
            # shutil.rmtree(app.config["OUTPUT_TEMP_FOLDER"])

            sse.publish(
                {"message": "Processing complete", "status": "complete"},
                type="process_update",
            )
        except Exception as e:
            print(f"Exception: {type(e)}\n{e.args}")
            sse.publish({"message": str(e)}, type="process_update")


@app.route("/process", methods=["POST"])
def process_files():
    session_id = session.get("session_id")
    threading.Thread(
        target=process_files_background, args=(session_id,)
    ).start()
    return Response("Processing started.", 202)


from flask import send_from_directory


@app.route("/download", methods=["GET"])
def download_file():
    session_id = session["session_id"]
    final_dir = os.path.join(app.config["FINAL_FOLDER"], session_id)
    try:
        return send_from_directory(
            directory=final_dir,
            path="output.zip",
            as_attachment=True,
        )
    except FileNotFoundError:
        abort(404)


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
    os.makedirs(output_dir)
    return "", 204


if __name__ == "__main__":
    print("Running App")
    app.run(debug=False)
