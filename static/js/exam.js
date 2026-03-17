const examApp = document.getElementById("examApp");
const examId = examApp.dataset.examId;
let questions = JSON.parse(document.getElementById("questions-data").textContent);
let currentQuestion = 0;
let answers = {};
let visited = {};
let examSubmitting = false;
let violations = 0;
let violationDetected = false;
let time = Number(examApp.dataset.examDuration) * 60;

function notifyExamEvent(status, incrementWarning = false) {
    const body = new URLSearchParams({
        exam_id: examId,
        status: status,
        increment_warning: incrementWarning ? "true" : "false",
    });

    return fetch("/exam-event", {
        method: "POST",
        headers: {
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
    }).catch(() => null);
}

function loadQuestion() {
    visited[currentQuestion] = true;

    let q = questions[currentQuestion];
    let html =
        "<h3>Question " + (currentQuestion + 1) + " / " + questions.length + "</h3>";
    html += "<p>" + q[2] + "</p>";
    html += `<label class="option"><input type="radio" name="opt" value="A" onclick="saveAnswer('A')"> ${q[3]}</label><br>`;
    html += `<label class="option"><input type="radio" name="opt" value="B" onclick="saveAnswer('B')"> ${q[4]}</label><br>`;
    html += `<label class="option"><input type="radio" name="opt" value="C" onclick="saveAnswer('C')"> ${q[5]}</label><br>`;
    html += `<label class="option"><input type="radio" name="opt" value="D" onclick="saveAnswer('D')"> ${q[6]}</label><br>`;

    document.getElementById("question-box").innerHTML = html;

    let qid = q[0];
    if (answers[qid]) {
        let radios = document.getElementsByName("opt");
        for (let r of radios) {
            if (r.value === answers[qid]) {
                r.checked = true;
            }
        }
    }

    updatePalette();
    updateCounter();
}

function saveAnswer(opt) {
    let qid = questions[currentQuestion][0];
    answers[qid] = opt;
    updateCounter();
    updatePalette();
}

function updateCounter() {
    let answered = Object.keys(answers).length;
    document.getElementById("answerCount").innerText =
        "Answered: " + answered + " / " + questions.length;
}

function nextQuestion() {
    if (currentQuestion < questions.length - 1) {
        currentQuestion++;
        loadQuestion();
    }
}

function prevQuestion() {
    if (currentQuestion > 0) {
        currentQuestion--;
        loadQuestion();
    }
}

function jumpQuestion(i) {
    currentQuestion = i;
    loadQuestion();
}

function buildPalette() {
    let html = "<span onclick='prevQuestion()'><</span>";

    for (let i = 0; i < questions.length; i++) {
        html += `<span id="p${i}" onclick="jumpQuestion(${i})">${i + 1}</span>`;
    }

    html += "<span onclick='nextQuestion()'>></span>";
    document.getElementById("palette").innerHTML = html;
}

function updatePalette() {
    for (let i = 0; i < questions.length; i++) {
        let el = document.getElementById("p" + i);
        if (!el) {
            continue;
        }

        let qid = questions[i][0];

        if (answers[qid]) {
            el.style.color = "green";
        } else if (visited[i]) {
            el.style.color = "orange";
        } else {
            el.style.color = "black";
        }

        el.style.textDecoration = i === currentQuestion ? "underline" : "none";
    }
}

function showPopup() {
    document.getElementById("popupOverlay").style.display = "flex";
}

function closePopup() {
    document.getElementById("popupOverlay").style.display = "none";
}

function showViolationPopup() {
    document.getElementById("violationOverlay").style.display = "flex";
}

function confirmViolationSubmit() {
    submitExam("Auto Submitted");
}

function submitExam(status = "Submitted") {
    if (examSubmitting) {
        return;
    }

    examSubmitting = true;
    document.getElementById("finalStatus").value = status;

    let form = document.getElementById("examForm");

    for (let qid in answers) {
        let input = document.createElement("input");
        input.type = "hidden";
        input.name = "q" + qid;
        input.value = answers[qid];
        form.appendChild(input);
    }

    notifyExamEvent(status, false);
    setTimeout(() => form.submit(), 50);
}

function startTimer() {
    setInterval(function () {
        let m = Math.floor(time / 60);
        let s = time % 60;

        document.getElementById("timer").innerText =
            m + ":" + (s < 10 ? "0" : "") + s;

        time--;

        if (time <= 0) {
            submitExam("Auto Submitted");
        }
    }, 1000);
}

function showWarning(txt) {
    let box = document.getElementById("warningBox");
    box.innerText = txt;
    box.style.display = "block";

    setTimeout(() => {
        box.style.display = "none";
    }, 3000);
}

document.addEventListener("visibilitychange", function () {
    if (document.hidden && !examSubmitting) {
        violations++;
        violationDetected = true;
        showWarning("Tab switching detected " + violations + "/1");
        notifyExamEvent("Warning Issued", true);
    } else if (!document.hidden && violationDetected && !examSubmitting) {
        showViolationPopup();
        violationDetected = false;
    }
});

document.addEventListener("keydown", function (e) {
    if (
        e.key === "F5" ||
        (e.ctrlKey && e.key.toLowerCase() === "r") ||
        (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "r")
    ) {
        e.preventDefault();
        e.stopPropagation();
        showWarning("Reload disabled during exam");
        notifyExamEvent("Warning Issued", true);
        return false;
    }
});

window.addEventListener("beforeunload", function (e) {
    if (!examSubmitting) {
        e.preventDefault();
        e.returnValue = "You will leave the exam and go back to dashboard.";
    }
});

buildPalette();
loadQuestion();
startTimer();

window.prevQuestion = prevQuestion;
window.nextQuestion = nextQuestion;
window.jumpQuestion = jumpQuestion;
window.saveAnswer = saveAnswer;
window.showPopup = showPopup;
window.closePopup = closePopup;
window.submitExam = submitExam;
window.confirmViolationSubmit = confirmViolationSubmit;
