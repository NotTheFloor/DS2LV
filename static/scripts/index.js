document.addEventListener("DOMContentLoaded", (event) => {
    const processButton = document.getElementById("process");
    const downloadButton = document.getElementById("downloadButton");
    const fileInput = document.querySelector('input[type="file"]');
    const uploadButton = document.querySelector('button[type="submit"]');
    const pendingUploadsList = document.getElementById("pendingUploads");
    const uploadedFilesList = document.getElementById("uploadedFiles");
    const processedFilesList = document.getElementById("processedFiles");

    // Handle file selection
    fileInput.addEventListener("change", function (event) {
        const files = event.target.files;
        for (let i = 0; i < files.length; i++) {
            const li = document.createElement("li");
            li.textContent = files[i].name;

            const removeButton = document.createElement("button");
            removeButton.textContent = "X";

            removeButton.addEventListener("click", function (event) {
                event.stopPropagation();

                const listItem = event.currentTarget.parentElement;
                const filename = listItem.textContent.slice(0, -1); // Remove the 'X' at the end

                // If the list item is in the 'Uploaded Files' list, delete the corresponding file from the server
                if (listItem.parentElement === uploadedFilesList) {
                    fetch("/delete-file", {
                        method: "DELETE",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify({ filename: filename }),
                    })
                        .then((response) => {
                            if (!response.ok) {
                                console.error(
                                    "Error deleting file, status code: " + response.status
                                );
                            }
                        })
                        .catch((error) => console.error("Error:", error));
                }

                // Remove the list item
                listItem.remove();
            });

            li.appendChild(removeButton);
            pendingUploadsList.appendChild(li);
        }
    });

    // Handle file upload
    uploadButton.addEventListener("click", function (event) {
        event.preventDefault();
        const formData = new FormData();
        const pendingUploads = Array.from(fileInput.files);
        pendingUploads.forEach((file) => {
            formData.append("file", file);
        });
        fetch("/", {
            method: "POST",
            body: formData,
        })
            .then((response) => {
                if (response.ok) {
                    // Move all list items from pendingUploads to uploadedFiles
                    Array.from(pendingUploadsList.children).forEach((li) => {
                        pendingUploadsList.removeChild(li);
                        uploadedFilesList.appendChild(li);
                    });
                } else {
                    console.error("Error uploading files, status code: " + response.status);
                }
            })
            .catch((error) => console.error("Error:", error));
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
                            // Find the list item for the processed file and remove it
                            Array.from(uploadedFilesList.children).forEach((li) => {
                                if (li.textContent.slice(0, -1) === data.filename) { // Remove the 'X' at the end
                                    li.remove();
                                }
                            });

                            // Create new list items for the output files and add them to the 'Uploaded Files' list
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
    });
});
