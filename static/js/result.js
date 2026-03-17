function toggleReview() {
    let section = document.getElementById("reviewSection");

    if (section.style.display === "none") {
        section.style.display = "block";
    } else {
        section.style.display = "none";
    }
}

history.pushState(null, null, location.href);

window.onpopstate = function () {
    history.go(1);
};
