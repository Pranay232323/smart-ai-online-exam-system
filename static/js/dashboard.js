const chatPopup = document.getElementById("chatPopup");
const chatBox = document.getElementById("chatBox");
const chatInput = document.getElementById("chatInput");

function toggleChat(openState) {
    const shouldOpen =
        typeof openState === "boolean"
            ? openState
            : !chatPopup.classList.contains("open");

    chatPopup.classList.toggle("open", shouldOpen);
    chatPopup.setAttribute("aria-hidden", shouldOpen ? "false" : "true");

    if (shouldOpen) {
        chatInput.focus();
    }
}

function appendMessage(text, sender) {
    const message = document.createElement("div");
    message.className = "message " + sender;
    message.textContent = text;
    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function askChatbot(message) {
    const response = await fetch("/student-chatbot", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
    });

    const data = await response.json();
    appendMessage(data.reply, "bot");
}

async function sendMessage() {
    const message = chatInput.value.trim();

    if (!message) {
        return;
    }

    toggleChat(true);
    appendMessage(message, "student");
    chatInput.value = "";

    try {
        await askChatbot(message);
    } catch (error) {
        appendMessage(
            "I could not reach the help service right now. Please try again in a moment.",
            "bot"
        );
    }
}

function sendPrompt(message) {
    chatInput.value = message;
    sendMessage();
}

chatInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
        sendMessage();
    }
});

document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && chatPopup.classList.contains("open")) {
        toggleChat(false);
    }
});
