const chartData = document.getElementById("chart-data");
const names = JSON.parse(chartData.dataset.names);
const scores = JSON.parse(chartData.dataset.scores);

const canvas = document.getElementById("myChart");
const context = canvas.getContext("2d");

function chartColors() {
    const styles = getComputedStyle(document.documentElement);
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const primary = styles.getPropertyValue("--primary").trim();
    const primaryDark = styles.getPropertyValue("--primary-dark").trim();
    const text = styles.getPropertyValue("--text").trim();
    const border = styles.getPropertyValue("--border").trim();

    const gradient = context.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, primary);
    gradient.addColorStop(1, primaryDark);

    return {
        gradient,
        text,
        border,
        grid: isDark ? "rgba(255,255,255,0.09)" : "rgba(23,50,77,0.08)",
    };
}

function buildConfig() {
    const colors = chartColors();
    return {
        type: "bar",
        data: {
            labels: names,
            datasets: [
                {
                    label: "Average Percentage",
                    data: scores,
                    backgroundColor: colors.gradient,
                    borderRadius: 14,
                    borderSkipped: false,
                    maxBarThickness: 42,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: colors.text,
                    },
                },
                tooltip: {
                    callbacks: {
                        label: function (item) {
                            return item.raw + "% average score";
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: colors.text,
                    },
                    grid: {
                        display: false,
                    },
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        color: colors.text,
                        callback: function (value) {
                            return value + "%";
                        },
                    },
                    grid: {
                        color: colors.grid,
                    },
                    border: {
                        color: colors.border,
                    },
                },
            },
        },
    };
}

const chart = new Chart(context, buildConfig());

new MutationObserver(() => {
    const config = buildConfig();
    chart.data = config.data;
    chart.options = config.options;
    chart.update();
}).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
});
