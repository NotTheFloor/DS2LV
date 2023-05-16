from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    Response,
    send_from_directory,
    abort,
)
from flask_sse import sse
import os, shutil, threading

import ds2logreader

app = Flask(__name__)

# Add the Redis URL to your application's configuration
# Replace "redis://localhost:6379" with your Redis server's URL if it's not on localhost
app.config["REDIS_URL"] = "redis://localhost"

app.register_blueprint(sse, url_prefix="/stream")

UPLOAD_FOLDER = "uploads"
ARCHIVE_FOLDER = "archive"
OUTPUT_TEMP_FOLDER = "output_temp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ARCHIVE_FOLDER"] = ARCHIVE_FOLDER
app.config["OUTPUT_TEMP_FOLDER"] = OUTPUT_TEMP_FOLDER

ds2 = ds2logreader.DS2LogReader(
    output_folder=app.config["OUTPUT_TEMP_FOLDER"], auto_run=False
)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        for file in request.files.getlist("file"):
            filename = file.filename
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        return redirect(url_for("index"))

    return render_template("index.html")


def process_files_background():
    with app.app_context():
        try:
            for filename in os.listdir(app.config["UPLOAD_FOLDER"]):
                if filename[0] == ".":
                    print(f"Skipping file {filename}")
                    continue

                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                print(f"Processing file {file_path}")
                before_files = set(
                    os.listdir(app.config["OUTPUT_TEMP_FOLDER"])
                )
                result = ds2.process_file(file_path)
                after_files = set(os.listdir(app.config["OUTPUT_TEMP_FOLDER"]))
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
                    os.path.join(app.config["ARCHIVE_FOLDER"], filename),
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
            shutil.make_archive(
                "final/output", "zip", app.config["OUTPUT_TEMP_FOLDER"]
            )
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
    threading.Thread(target=process_files_background).start()
    return Response("Processing started.", 202)


from flask import send_from_directory


@app.route("/download", methods=["GET"])
def download_file():
    try:
        return send_from_directory(
            directory="final",
            path="output.zip",
            as_attachment=True,
        )
    except FileNotFoundError:
        abort(404)


@app.route("/delete-file", methods=["DELETE"])
def delete_file():
    data = request.get_json()
    filename = data.get("filename")
    if filename:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return "", 204
        else:
            return "File not found", 404
    else:
        return "Filename not provided", 400


if __name__ == "__main__":
    app.run(debug=True)
