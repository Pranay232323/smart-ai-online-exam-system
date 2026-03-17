const chartData = document.getElementById("chart-data");
const names = JSON.parse(chartData.dataset.names);
const scores = JSON.parse(chartData.dataset.scores);

new Chart(document.getElementById("myChart"), {
    type: "bar",
    data: {
        labels: names,
        datasets: [
            {
                label: "Average Percentage",
                data: scores,
            },
        ],
    },
});
