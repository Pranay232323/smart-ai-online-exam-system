const examApp = document.getElementById("examApp");
const examId = examApp.dataset.examId;
const warningLimit = Number(examApp.dataset.warningLimit || 3);
const questions = JSON.parse(document.getElementById("questions-data").textContent);
const storageKey = "exam_state_" + examId;
const fullscreenGate = document.getElementById("fullscreenGate");

let currentQuestion = 0;
let answers = {};
let visited = {};
let examSubmitting = false;
let warnings = 0;
let pendingViolationMessage = "";
let violationDetected = false;
let time = Number(examApp.dataset.examDuration) * 60;

function saveExamState() {
    if (examSubmitting) {
        return;
    }

    sessionStorage.setItem(
        storageKey,
        JSON.stringify({
            currentQuestion,
            answers,
            visited,
            warnings,
            time,
        })
    );
}

function clearExamState() {
    sessionStorage.removeItem(storageKey);
}

function restoreExamState() {
    const rawState = sessionStorage.getItem(storageKey);
    if (!rawState) {
        return false;
    }

    try {
        const state = JSON.parse(rawState);
        currentQuestion = typeof state.currentQuestion === "number" ? state.currentQuestion : 0;
        answers = state.answers || {};
        visited = state.visited || {};
        warnings = typeof state.warnings === "number" ? state.warnings : 0;
        time = typeof state.time === "number" ? state.time : time;
        return true;
    } catch (error) {
        sessionStorage.removeItem(storageKey);
        return false;
    }
}

function isReloadNavigation() {
    const navigationEntries = performance.getEntriesByType("navigation");
    if (navigationEntries.length > 0) {
        return navigationEntries[0].type === "reload";
    }

    return performance.navigation && performance.navigation.type === 1;
}

function updateWarningCounter() {
    const warningCount = document.getElementById("warningCount");
    if (warningCount) {
        warningCount.innerText = warnings + " / " + warningLimit;
    }
}

function notifyExamEvent(eventType, message, incrementWarning = false, status = "") {
    const body = new URLSearchParams({
        exam_id: examId,
        event_type: eventType,
        message: message,
        increment_warning: incrementWarning ? "true" : "false",
        status: status,
    });

    return fetch("/exam-event", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
    })
        .then((response) => response.json())
        .catch(() => null);
}

function loadQuestion() {
    visited[currentQuestion] = true;

    const q = questions[currentQuestion];
    let html =
        "<h3>Question " + (currentQuestion + 1) + " / " + questions.length + "</h3>";
    html += "<p>" + q[2] + "</p>";
    html += `<label class="option"><input type="radio" name="opt" value="A" onclick="saveAnswer('A')"> ${q[3]}</label>`;
    html += `<label class="option"><input type="radio" name="opt" value="B" onclick="saveAnswer('B')"> ${q[4]}</label>`;
    html += `<label class="option"><input type="radio" name="opt" value="C" onclick="saveAnswer('C')"> ${q[5]}</label>`;
    html += `<label class="option"><input type="radio" name="opt" value="D" onclick="saveAnswer('D')"> ${q[6]}</label>`;

    document.getElementById("question-box").innerHTML = html;

    const qid = q[0];
    if (answers[qid]) {
        const radios = document.getElementsByName("opt");
        for (const radio of radios) {
            if (radio.value === answers[qid]) {
                radio.checked = true;
            }
        }
    }

    updatePalette();
    updateCounter();
    saveExamState();
}

function saveAnswer(option) {
    const qid = questions[currentQuestion][0];
    answers[qid] = option;
    updateCounter();
    updatePalette();
    saveExamState();
}

function updateCounter() {
    const answered = Object.keys(answers).length;
    document.getElementById("answerCount").innerText =
        answered + " / " + questions.length;
}

function nextQuestion() {
    if (currentQuestion < questions.length - 1) {
        currentQuestion += 1;
        loadQuestion();
    }
}

function prevQuestion() {
    if (currentQuestion > 0) {
        currentQuestion -= 1;
        loadQuestion();
    }
}

function jumpQuestion(index) {
    currentQuestion = index;
    loadQuestion();
}

function buildPalette() {
    let html = "<span onclick='prevQuestion()'><</span>";
    for (let i = 0; i < questions.length; i += 1) {
        html += `<span id="p${i}" onclick="jumpQuestion(${i})">${i + 1}</span>`;
    }
    html += "<span onclick='nextQuestion()'>></span>";
    document.getElementById("palette").innerHTML = html;
}

function updatePalette() {
    for (let i = 0; i < questions.length; i += 1) {
        const element = document.getElementById("p" + i);
        if (!element) {
            continue;
        }

        const qid = questions[i][0];
        if (answers[qid]) {
            element.style.color = "green";
        } else if (visited[i]) {
            element.style.color = "orange";
        } else {
            element.style.color = "black";
        }

        element.style.textDecoration = i === currentQuestion ? "underline" : "none";
    }
}

function showPopup() {
    document.getElementById("popupOverlay").style.display = "flex";
}

function closePopup() {
    document.getElementById("popupOverlay").style.display = "none";
}

function showViolationPopup(message) {
    document.getElementById("violationMessage").innerText = message;
    document.getElementById("violationOverlay").style.display = "flex";
}

function confirmViolationSubmit() {
    submitExam("Auto Submitted");
}

function appendHiddenAnswers(form) {
    Array.from(form.querySelectorAll("input[data-answer='true']")).forEach((input) => {
        input.remove();
    });

    Object.keys(answers).forEach((qid) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "q" + qid;
        input.value = answers[qid];
        input.dataset.answer = "true";
        form.appendChild(input);
    });
}

function submitExam(status = "Submitted") {
    if (examSubmitting) {
        return;
    }

    examSubmitting = true;
    clearExamState();
    document.getElementById("finalStatus").value = status;

    const form = document.getElementById("examForm");
    appendHiddenAnswers(form);
    notifyExamEvent(status, "Exam submitted", false, status);
    setTimeout(() => form.submit(), 50);
}

function startTimer() {
    setInterval(() => {
        const minutes = Math.floor(time / 60);
        const seconds = time % 60;

        document.getElementById("timer").innerText =
            minutes + ":" + (seconds < 10 ? "0" : "") + seconds;

        time -= 1;
        saveExamState();
        if (time <= 0) {
            submitExam("Auto Submitted");
        }
    }, 1000);
}

function showWarning(message) {
    const box = document.getElementById("warningBox");
    box.innerText = message;
    box.style.display = "block";

    setTimeout(() => {
        box.style.display = "none";
    }, 3500);
}

function registerViolation(eventType, message) {
    if (examSubmitting) {
        return;
    }

    notifyExamEvent(eventType, message, true).then((data) => {
        warnings = data && typeof data.warning_count === "number" ? data.warning_count : warnings + 1;
        updateWarningCounter();
        showWarning(message + " (" + warnings + "/" + warningLimit + ")");
        saveExamState();

        if (data && data.should_auto_submit) {
            pendingViolationMessage =
                "You crossed the allowed warning limit. Your exam will now be submitted.";
        } else {
            pendingViolationMessage = message + " This warning has been logged.";
        }
        violationDetected = true;
    });
}

function requestFullscreenMode() {
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
        return document.documentElement.requestFullscreen().catch(() => null);
    }
    return Promise.resolve();
}

function enableFullscreenGuard() {
    const tryFullscreen = () => {
        if (!document.fullscreenElement && !examSubmitting) {
            requestFullscreenMode();
        }
    };

    ["click", "keydown", "touchstart"].forEach((eventName) => {
        document.addEventListener(eventName, tryFullscreen, { passive: true });
    });
}

function hideFullscreenGate() {
    if (fullscreenGate) {
        fullscreenGate.classList.add("hidden");
    }
}

function enterExamMode() {
    requestFullscreenMode().finally(() => {
        hideFullscreenGate();
    });
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden && !examSubmitting) {
        registerViolation("Tab Switch", "Tab switching was detected during the exam.");
    } else if (!document.hidden && violationDetected && !examSubmitting) {
        showViolationPopup(pendingViolationMessage);
        violationDetected = false;
    }
});

document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && !examSubmitting) {
        notifyExamEvent(
            "Fullscreen Exit",
            "Fullscreen was exited during the exam. The exam will be auto-submitted.",
            true
        ).then((data) => {
            warnings =
                data && typeof data.warning_count === "number" ? data.warning_count : warnings + 1;
            updateWarningCounter();
            pendingViolationMessage =
                "You exited fullscreen during the exam. This violates the exam rules, so your exam will now be submitted.";
            showViolationPopup(pendingViolationMessage);
        });
    }
});

["copy", "paste", "cut", "contextmenu"].forEach((eventName) => {
    document.addEventListener(eventName, (event) => {
        if (examSubmitting) {
            return;
        }

        event.preventDefault();
        registerViolation(
            eventName.toUpperCase(),
            eventName.charAt(0).toUpperCase() + eventName.slice(1) + " is blocked during the exam."
        );
    });
});

document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    const blockedShortcut =
        event.key === "F5" ||
        (event.ctrlKey && key === "r") ||
        (event.ctrlKey && key === "c") ||
        (event.ctrlKey && key === "v") ||
        (event.ctrlKey && key === "x") ||
        (event.ctrlKey && event.shiftKey && key === "r");

    if (blockedShortcut) {
        event.preventDefault();
        event.stopPropagation();
        registerViolation("Blocked Shortcut", "A restricted keyboard shortcut was used.");
        return false;
    }

    return true;
});

window.addEventListener("beforeunload", (event) => {
    if (!examSubmitting) {
        saveExamState();
        event.preventDefault();
        event.returnValue = "You are leaving an active exam.";
    }
});

restoreExamState();
buildPalette();
loadQuestion();
updateWarningCounter();
startTimer();
enableFullscreenGuard();

if (isReloadNavigation() && !examSubmitting) {
    pendingViolationMessage =
        "The exam page was reloaded. Reloading is not allowed during the exam, so your exam will now be submitted.";
    notifyExamEvent("Page Reload", pendingViolationMessage, true).then((data) => {
        warnings = data && typeof data.warning_count === "number" ? data.warning_count : warnings + 1;
        updateWarningCounter();
        showViolationPopup(pendingViolationMessage);
    });
}

window.prevQuestion = prevQuestion;
window.nextQuestion = nextQuestion;
window.jumpQuestion = jumpQuestion;
window.saveAnswer = saveAnswer;
window.showPopup = showPopup;
window.closePopup = closePopup;
window.submitExam = submitExam;
window.confirmViolationSubmit = confirmViolationSubmit;
window.requestFullscreenMode = requestFullscreenMode;
window.enterExamMode = enterExamMode;
