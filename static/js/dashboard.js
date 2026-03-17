const chatPopup = document.getElementById("chatPopup");
const chatBox = document.getElementById("chatBox");
const chatInput = document.getElementById("chatInput");
const rulesPopup = document.getElementById("rulesPopup");
const confirmStartExam = document.getElementById("confirmStartExam");
const rulesExamTitle = document.getElementById("rulesExamTitle");
const rulesTriggers = document.querySelectorAll(".rules-trigger");

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

function openRulesPopup(examId, examTitle) {
    confirmStartExam.href = "/start-exam/" + examId;
    rulesExamTitle.textContent =
        'You are about to start "' +
        examTitle +
        '". Please read these instructions carefully before continuing.';
    rulesPopup.classList.add("open");
    rulesPopup.setAttribute("aria-hidden", "false");
}

function closeRulesPopup() {
    rulesPopup.classList.remove("open");
    rulesPopup.setAttribute("aria-hidden", "true");
}

rulesTriggers.forEach(function (button) {
    button.addEventListener("click", function () {
        openRulesPopup(button.dataset.examId, button.dataset.examTitle);
    });
});

document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && rulesPopup.classList.contains("open")) {
        closeRulesPopup();
    }
});

window.closeRulesPopup = closeRulesPopup;
