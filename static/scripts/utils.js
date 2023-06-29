export var rcSuccess = function (result) {
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

export function formatFileSize(bytes) {
    if (bytes < 1024) {
        return bytes + ' Bytes';
    } else if (bytes < 1048576) {
        return (bytes / 1024).toFixed(0) + ' KB';
    } else {
        return (bytes / 1048576).toFixed(0) + ' MB';
    }
}