document.addEventListener("DOMContentLoaded", (event) => {
    const processButton = document.getElementById("process");
    const downloadButton = document.getElementById("downloadButton");
    const fileInput = document.querySelector('input[type="file"]');
    const filesList = document.getElementById("files");
    const processedFilesList = document.getElementById("processedFiles");

    // Handle file selection
    fileInput.addEventListener("change", function (event) {
        const files = event.target.files;
        for (let i = 0; i < files.length; i++) {
            const filename = files[i].name;

            // Create an li item with "Uploading" status
            const li = document.createElement("li");
            li.textContent = filename + " (Uploading)";
            filesList.appendChild(li);

            // Upload the file
            const formData = new FormData();
            formData.append("file", files[i]);
            fetch("/", {
                method: "POST",
                body: formData,
            })
                .then((response) => {
                    if (response.ok) {
                        li.textContent = filename + " (Complete)";
                    } else {
                        console.error("Error uploading file, status code: " + response.status);
                        li.textContent = filename + " (Error)";
                    }
                })
                .catch((error) => {
                    console.error("Error:", error);
                    li.textContent = filename + " (Error)";
                });
        }
    });

    processButton.addEventListener("click", (event) => {
        event.preventDefault();

        fetch("/process", { method: "POST" })
            .then((response) => {
                if (response.status === 202) {
                    // Initiate Server-Sent Events
                    var source = new EventSource("/stream");
                    source.addEventListener('process_update', function (event) {
                        console.log(event.data); // Log all messages for debugging
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
                            document.getElementById("downloadButton").disabled = false;
                            source.close();
                        }
                    }, false);
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
