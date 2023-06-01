var rcSuccess = function (result) {
    // Create the request body
    const requestBody = {
        'g-recaptcha-response': result,
    };

    // Validate recap
    fetch("/recap", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
    })
        .then((response) => {
            if (response.ok) {
                document.getElementById("uploadFileInput").disabled = false;
                document.getElementById("rc-div").hidden = true;

            } else {
                // Should do additional error reporting here
                console.error("Error recap, status code: " + response.status);
            }
        })
        .catch((error) => {
            console.error("Error:", error);
        });

};

function formatFileSize(bytes) {
    if (bytes < 1024) {
        return bytes + ' Bytes';
    } else if (bytes < 1048576) {
        return (bytes / 1024).toFixed(0) + ' KB';
    } else {
        return (bytes / 1048576).toFixed(0) + ' MB';
    }
}

document.addEventListener("DOMContentLoaded", (event) => {
    const processButton = document.getElementById("process");
    const downloadButton = document.getElementById("downloadButton");
    const fileInput = document.querySelector('input[type="file"]');
    const filesList = document.getElementById('filesBody');
    const processStatus = document.getElementById("processStatus");

    const emailForm = document.querySelector("#emailDialog form");
    const emailResultsButton = document.getElementById("emailResultsButton");
    const emailDialog = document.getElementById("emailDialog");
    const emailCancel = document.getElementById("emailCancel");

    // Get a reference to the dialog and the submit button
    var dialog = document.getElementById('feedbackDialog');
    var feedbackSubmit = document.getElementById('feedbackSubmit');

    let openProcessing = 0;
    processStatus.innerText = "Please select files to get started";

    // Open the dialog when the feedback button is clicked
    document.getElementById('feedbackButton').onclick = function () {
        dialog.showModal();
    };

    // Close the dialog when the cancel button is clicked
    dialog.querySelector('[value=cancel]').onclick = function () {
        dialog.close();
    };

    if (window.location.hostname === "127.0.0.1") {
        document.getElementById("uploadFileInput").disabled = false;
        document.getElementById("rc-div").hidden = true;
    };

    emailResultsButton.addEventListener("click", () => {
        emailDialog.showModal();
    });

    emailCancel.addEventListener("click", () => {
        emailDialog.close();
    });

    var resetPage = function () {
        // Remove all items from the 'Files' list
        while (filesList.firstChild) {
            filesList.removeChild(filesList.firstChild);
        }

        // Disable Download button
        downloadButton.disabled = true;
        emailResultsButton.disabled = true;
        document.getElementById("uploadFileInput").value = "";
        processStatus.innerText = "Please select files to get started";
        document.getElementById("uploadFileInput").disabled = false;

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
    };

    emailForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const emailInput = document.getElementById("emailAddress");
        const email = emailInput.value;

        // Create the request body
        const requestBody = {
            email_address: email,
        };

        // Send the POST request to the server
        fetch("/email", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody),
        })
            .then((response) => {
                if (response.ok) {
                    // Handle successful response
                    console.log("Email sent successfully");
                    // Close the dialog after successful email submission
                    emailDialog.close();
                } else {
                    // Handle error response
                    console.error("Error sending email:", response.status);
                }
            })
            .catch((error) => {
                // Handle network or other errors
                console.error("Error sending email:", error);
            });

        resetPage()
    });

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
        var totalFileSize = 0;
        var totalUploaded = 0;

        processStatus.innerText = "Please wait for files to finish uploading (0%)";

        for (let i = 0; i < files.length; i++) {
            const filename = files[i].name;
            const filesize = files[i].size;
            var lastLoaded = 0;
            totalFileSize += files[i].size;


            // Create a table row and cells for filename, filesize and status
            const tr = document.createElement("tr");
            const tdName = document.createElement("td");
            const tdSize = document.createElement("td");
            const tdStatus = document.createElement("td");

            tdName.textContent = filename;
            tdSize.textContent = formatFileSize(filesize);

            tr.appendChild(tdName);
            tr.appendChild(tdSize);
            tr.appendChild(tdStatus);
            filesList.appendChild(tr);

            if (!filename.endsWith(".csv")) {
                tdStatus.textContent = "Error: CSV extensions only";
                tr.classList.add("error");
                continue;
            }

            openProcessing += 1;
            processButton.disabled = true;

            tdStatus.textContent = "Uploading";
            tr.classList.remove("error");
            tr.classList.add("uploading");

            // Upload the file
            const formData = new FormData();
            formData.append("file", files[i]);

            // Use XMLHttpRequest instead of fetch
            const xhr = new XMLHttpRequest();

            // Listen to the 'progress' event
            xhr.upload.addEventListener('progress', function (e) {
                if (e.lengthComputable) {
                    // Calculate the percentage of the upload
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    totalUploaded += e.loaded - lastLoaded;
                    lastLoaded = e.loaded;
                    // Update the status cell with the progress
                    tdStatus.textContent = "Uploading (" + percentComplete + "%)";
                    const totalPercentComplete = Math.round((totalUploaded / totalFileSize) * 100);
                    processStatus.innerText = "Please wait for files to finish uploading (" + totalPercentComplete + "%)";
                }
            }, false);

            // Listen to the 'load' event
            xhr.addEventListener('load', function (e) {
                // Update the status cell based on the HTTP status code
                if (xhr.status == 200) {
                    tdStatus.textContent = "Complete";
                    tr.classList.remove("uploading");
                    tr.classList.add("completed");
                    openProcessing -= 1;

                    sortTableRows();

                    if (openProcessing <= 0) {
                        processButton.disabled = false;
                        processStatus.innerText = "Uploading complete. Ready to Process";
                    }
                } else {
                    console.error("Error uploading file, status code: " + xhr.status);
                    tdStatus.textContent = "Error";
                }
            });

            // Listen to the 'error' event
            xhr.addEventListener('error', function (e) {
                console.error("Error:", e);
                tdStatus.textContent = "Error";
                tr.classList.remove("uploading");
                tr.classList.add("error");
            });

            // Open and send the request
            xhr.open("POST", "/", true);
            xhr.send(formData);
        }
    });

    // Sort the table rows based on the upload status
    function sortTableRows() {
        const tableBody = document.getElementById("filesBody");
        const rows = Array.from(tableBody.getElementsByTagName("tr"));

        rows.sort(function (a, b) {
            const aStatus = a.cells[2].textContent;
            const bStatus = b.cells[2].textContent;

            if (aStatus === "Complete" && bStatus !== "Complete") {
                return 1;
            } else if (aStatus !== "Complete" && bStatus === "Complete") {
                return -1;
            } else {
                return 0;
            }
        });

        rows.forEach(function (row) {
            tableBody.appendChild(row);
        });
    }

    processButton.addEventListener("click", (event) => {
        event.preventDefault();

        document.getElementById("uploadFileInput").disabled = true;

        processStatus.innerText = "Starting...";

        var source = new EventSource("/stream");
        source.addEventListener('process_update', function (event) {
            var data = JSON.parse(event.data);
            if (data.message) {
                processStatus.innerText = data.message;
            }
            if (data.status === "fileComplete") {
                const rows = document.querySelectorAll("#filesBody tr");

                rows.forEach((row) => {
                    const fileNameCell = row.querySelector("td:first-child");
                    const statusCell = row.querySelector("td:nth-child(3)");

                    if (fileNameCell.textContent === data.inputFile) {
                        row.classList.remove("completed");
                        row.classList.add("processed");
                        statusCell.textContent = "Processed";
                    }
                });
            }
            if (data.status === "complete") {
                emailResultsButton.disabled = false;
                downloadButton.disabled = false;
                processButton.disabled = true;
                source.close();
            }
        }, false);

        fetch("/process", { method: "POST" })
            .then((response) => {
                if (response.status !== 202) {
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

        resetPage();
    });

    function deleteFile(filename) {
        // Make a request to the delete-file endpoint with the filename as an argument
        fetch("/delete-file?filename=" + encodeURIComponent(filename), {
            method: "DELETE"
        })
            .then((response) => {
                if (response.ok) {
                    // Delete the table row from the DOM
                    tr.remove();
                    console.log("File deleted successfully.");
                } else {
                    console.error("Error deleting file, status code: " + response.status);
                }
            })
            .catch((error) => {
                console.error("Error:", error);
            });
    }
});
