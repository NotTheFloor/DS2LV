var rcSuccess = function () {
    document.getElementById("uploadFileInput").disabled = false;
    document.getElementById("rc-div").hidden = true;
};

document.addEventListener("DOMContentLoaded", (event) => {
    const processButton = document.getElementById("process");
    const downloadButton = document.getElementById("downloadButton");
    const fileInput = document.querySelector('input[type="file"]');
    const filesList = document.getElementById("files");
    const processedFilesList = document.getElementById("processedFiles");
    const fileUploadError = document.getElementById("fileUploadError");
    let openProcessing = 0;

    // Get a reference to the dialog and the submit button
    var dialog = document.getElementById('feedbackDialog');
    var feedbackSubmit = document.getElementById('feedbackSubmit');

    // Open the dialog when the feedback button is clicked
    document.getElementById('feedbackButton').onclick = function () {
        dialog.showModal();
    };

    // Close the dialog when the cancel button is clicked
    dialog.querySelector('[value=cancel]').onclick = function () {
        dialog.close();
    };

    // Send feedback when the submit button is clicked
    feedbackSubmit.onclick = function () {
        let feedbackText = document.getElementById("feedbackText").value;
        if (feedbackText.length === 0) {
            alert("Please enter some feedback before submitting");
        } else {
            fetch("/feedback", {
                method: "POST",
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ feedback: feedbackText }),
            })
                .then(response => {
                    if (response.ok) {
                        alert("Thank you for your feedback!");
                        dialog.close();
                    } else {
                        throw new Error("Network response was not ok");
                    }
                })
                .catch(error => {
                    alert("An error occurred while submitting your feedback. Please try again later.");
                    console.error('There has been a problem with your fetch operation:', error);
                });
        }
    };


    // Handle file selection
    fileInput.addEventListener("change", function (event) {
        const files = event.target.files;
        for (let i = 0; i < files.length; i++) {
            const filename = files[i].name;
            const filesize = files[i].size; // Add this line to get file size

            // Create a table row and cells for filename, filesize and status
            const tr = document.createElement("tr");
            const tdName = document.createElement("td");
            const tdSize = document.createElement("td");
            const tdStatus = document.createElement("td");

            tdName.textContent = filename;
            tdSize.textContent = filesize + ' bytes'; // You can format the size as needed

            tr.appendChild(tdName);
            tr.appendChild(tdSize);
            tr.appendChild(tdStatus);
            filesList.appendChild(tr);

            if (!filename.endsWith(".csv")) {
                tdStatus.textContent = "Error: CSV extensions only";
                tr.style.color = "#FFAAAA";
                continue;
            }

            // Include g-recaptcha-response in your request
            const recaptchaResponse = grecaptcha.getResponse();

            if (recaptchaResponse.length === 0 && !document.getElementById("rc-div").hidden) {
                fileUploadError.innerText = "Please complete the reCAPTCHA";
                fileUploadError.hidden = false;
                fileUploadError.style.color = "#FFAAAA";
                return;
            }

            openProcessing += 1;
            processButton.disabled = true;

            tdStatus.textContent = "Uploading";

            // Upload the file
            const formData = new FormData();
            formData.append("file", files[i]);

            if (recaptchaResponse) {
                formData.append("g-recaptcha-response", recaptchaResponse);
            }

            fetch("/", {
                method: "POST",
                body: formData,
            })
                .then((response) => {
                    if (response.ok) {
                        tdStatus.textContent = "Complete";
                        openProcessing -= 1;

                        if (openProcessing <= 0) processButton.disabled = false;
                    } else {
                        console.error("Error uploading file, status code: " + response.status);
                        tdStatus.textContent = "Error";
                    }
                })
                .catch((error) => {
                    console.error("Error:", error);
                    tdStatus.textContent = "Error";
                });
        }
    });

    processButton.addEventListener("click", (event) => {
        event.preventDefault();

        document.getElementById("processStatus").innerText = "Starting...";

        var source = new EventSource("/stream");
        source.addEventListener('process_update', function (event) {
            var data = JSON.parse(event.data);
            if (data.message) {
                document.getElementById("processStatus").innerText = data.message;
            }
            if (data.status === "fileComplete") {
                // Remove the li item for the processed file
                Array.from(filesList.children).forEach((li) => {
                    if (li.textContent.startsWith(data.filename)) {
                        li.remove();
                    }
                });

                // Create new li items for the output
                // files and add them to the 'Processed Files' list
                data.outputFiles.forEach((filename) => {
                    const li = document.createElement("li");
                    li.textContent = filename;
                    processedFilesList.appendChild(li);
                });
            }
            if (data.status === "complete") {
                downloadButton.disabled = false;
                processButton.disabled = true;
                source.close();
            }
        }, false);

        fetch("/process", { method: "POST" })
            .then((response) => {
                if (response.status === 202) {
                    console.log(":)");
                } else {
                    console.error(
                        "Error starting processing, status code: " + response.status
                    );
                }
            })
            .catch((error) => console.error("Error:", error));
    });

    downloadButton.addEventListener('click', (event) => {
        event.preventDefault();
        window.location.href = "/download";

        // Remove all items from the 'Processed Files' list
        while (processedFilesList.firstChild) {
            processedFilesList.removeChild(processedFilesList.firstChild);
        }

        // Remove all items from the 'Files' list
        while (filesList.firstChild) {
            filesList.removeChild(filesList.firstChild);
        }

        // Disable Download button
        downloadButton.disabled = true;
        document.getElementById("uploadFileInput").value = "";
        document.getElementById("processStatus").innerText = "";

        // Request the server to reset the files and folders
        fetch("/reset", { method: "POST" })
            .then((response) => {
                if (response.ok) {
                    console.log("Reset successful.");
                } else {
                    console.error("Error resetting files and folders, status code: " + response.status);
                }
            })
            .catch((error) => {
                console.error("Error:", error);
            });
    });
});
