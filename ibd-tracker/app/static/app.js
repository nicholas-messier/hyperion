// IBD Tracker Frontend Logic

const BRISTOL_DESCRIPTIONS = {
    1: "Type 1 - Hard Lumps (Severe Constipation)",
    2: "Type 2 - Sausage Lumpy (Mild Constipation)",
    3: "Type 3 - Sausage with Cracks (Normal)",
    4: "Type 4 - Smooth Snake (Optimal Normal)",
    5: "Type 5 - Soft Blobs (Lacking Fiber)",
    6: "Type 6 - Mushy / Ragged (Mild Diarrhea)",
    7: "Type 7 - Watery Liquid (Severe Diarrhea)"
};

let frequencyChart = null;
let trendChart = null;

// DOM Elements
const timeRangeSelect = document.getElementById("timeRangeSelect");
const todayCountBadge = document.getElementById("todayCountBadge");
const metricTodayCount = document.getElementById("metricTodayCount");
const metricTodayStatus = document.getElementById("metricTodayStatus");
const metricAvgDaily = document.getElementById("metricAvgDaily");
const metricAvgBristol = document.getElementById("metricAvgBristol");
const metricBristolLabel = document.getElementById("metricBristolLabel");
const metricAvgPain = document.getElementById("metricAvgPain");
const metricBloodPct = document.getElementById("metricBloodPct");
const metricBloodEvents = document.getElementById("metricBloodEvents");
const tableWindowLabel = document.getElementById("tableWindowLabel");
const dailyTableBody = document.getElementById("dailyTableBody");
const recentTableBody = document.getElementById("recentTableBody");

// Modal Elements
const openLogModalBtn = document.getElementById("openLogModalBtn");
const closeLogModalBtn = document.getElementById("closeLogModalBtn");
const cancelModalBtn = document.getElementById("cancelModalBtn");
const logModal = document.getElementById("logModal");
const logForm = document.getElementById("logForm");
const bristolSelector = document.getElementById("bristolSelector");
const bristolInput = document.getElementById("bristolInput");
const bristolValueDisplay = document.getElementById("bristolValueDisplay");
const painRange = document.getElementById("painRange");
const painValueDisplay = document.getElementById("painValueDisplay");
const bloodSelector = document.getElementById("bloodSelector");
const toast = document.getElementById("toast");
const printReportBtn = document.getElementById("printReportBtn");
const printDateRange = document.getElementById("printDateRange");
const printGenDate = document.getElementById("printGenDate");

// Toast Notification
function showToast(message, duration = 3000) {
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, duration);
}

// Bristol Badge Helper
function getBristolBadge(score) {
    if (score === null || score === undefined) return '<span class="text-muted">--</span>';
    const rounded = Math.round(score);
    let badgeClass = "badge-normal";
    if (rounded <= 2) badgeClass = "badge-constipated";
    else if (rounded >= 5) badgeClass = "badge-diarrhea";
    return `<span class="badge ${badgeClass}">Type ${score}</span>`;
}

// Blood Badge Helper
function getBloodBadge(blood) {
    if (blood === "none") return '<span class="badge badge-blood-none">None</span>';
    if (blood === "some") return '<span class="badge badge-blood-some">Some / Trace</span>';
    if (blood === "alot") return '<span class="badge badge-blood-alot">A Lot</span>';
    return blood;
}

// Format Date / Time
function formatDateTime(isoString) {
    try {
        const d = new Date(isoString);
        return d.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit"
        });
    } catch (e) {
        return isoString;
    }
}

// Fetch and Refresh Data
async function loadDashboard() {
    const days = timeRangeSelect.value;
    tableWindowLabel.textContent = `Last ${days} Days`;
    printDateRange.textContent = `Last ${days} Days`;
    printGenDate.textContent = new Date().toLocaleString();

    try {
        const [statsRes, todayRes] = await Promise.all([
            fetch(`/api/stats?days=${days}`).then(r => r.json()),
            fetch(`/api/today`).then(r => r.json())
        ]);

        // Update Today Badges
        const todayCount = todayRes.today_count;
        todayCountBadge.textContent = todayCount;
        metricTodayCount.textContent = todayCount;
        metricTodayStatus.textContent = todayCount === 1 ? "1 movement today" : `${todayCount} movements today`;

        // Update Summary Metrics
        const sum = statsRes.summary;
        metricAvgDaily.textContent = sum.avg_daily_count.toFixed(1);
        
        if (sum.avg_bristol !== null) {
            metricAvgBristol.textContent = sum.avg_bristol.toFixed(1);
            if (sum.avg_bristol < 3) {
                metricBristolLabel.innerHTML = '<span class="badge badge-constipated">Constipation Trend</span>';
            } else if (sum.avg_bristol > 4.5) {
                metricBristolLabel.innerHTML = '<span class="badge badge-diarrhea">Diarrhea / Loose Trend</span>';
            } else {
                metricBristolLabel.innerHTML = '<span class="badge badge-normal">Normal Range</span>';
            }
        } else {
            metricAvgBristol.textContent = "--";
            metricBristolLabel.textContent = "No data in window";
        }

        metricAvgPain.textContent = sum.avg_pain !== null ? sum.avg_pain.toFixed(1) : "--";
        metricBloodPct.textContent = `${sum.blood_incidence_pct}%`;
        
        const totalBloodEvents = (sum.blood_events.some || 0) + (sum.blood_events.alot || 0);
        metricBloodEvents.textContent = `${totalBloodEvents} blood events (${sum.blood_events.some} some, ${sum.blood_events.alot} a lot)`;

        // Render Charts
        renderCharts(statsRes.daily_breakdown);

        // Render Daily Breakdown Table
        renderDailyTable(statsRes.daily_breakdown);

        // Render Recent Logs Table
        renderRecentTable(statsRes.recent_logs);

    } catch (err) {
        console.error("Failed to load dashboard data:", err);
        showToast("Error loading tracker data");
    }
}

// Render Charts with Chart.js
function renderCharts(dailyData) {
    const labels = dailyData.map(d => d.date);
    const counts = dailyData.map(d => d.count);
    const bristolAvg = dailyData.map(d => d.avg_bristol);
    const painAvg = dailyData.map(d => d.avg_pain);

    // 1. Frequency Bar Chart
    const ctxFreq = document.getElementById("frequencyChart").getContext("2d");
    if (frequencyChart) frequencyChart.destroy();

    frequencyChart = new Chart(ctxFreq, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "Bowel Movements",
                data: counts,
                backgroundColor: "rgba(2, 132, 199, 0.7)",
                borderColor: "#0284c7",
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { precision: 0 },
                    title: { display: true, text: "Count / Day" }
                },
                x: {
                    ticks: { maxRotation: 45, minRotation: 0 }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    // 2. Trend Dual Line Chart (Bristol + Pain)
    const ctxTrend = document.getElementById("trendChart").getContext("2d");
    if (trendChart) trendChart.destroy();

    trendChart = new Chart(ctxTrend, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Avg Bristol Scale",
                    data: bristolAvg,
                    borderColor: "#10b981",
                    backgroundColor: "rgba(16, 185, 129, 0.1)",
                    borderWidth: 2,
                    tension: 0.2,
                    yAxisID: "yBristol",
                    fill: false
                },
                {
                    label: "Avg Pain Level",
                    data: painAvg,
                    borderColor: "#ef4444",
                    backgroundColor: "rgba(239, 68, 68, 0.1)",
                    borderWidth: 2,
                    borderDash: [5, 5],
                    tension: 0.2,
                    yAxisID: "yPain",
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                yBristol: {
                    type: "linear",
                    position: "left",
                    min: 1,
                    max: 7,
                    ticks: { stepSize: 1 },
                    title: { display: true, text: "Bristol Scale (1-7)" }
                },
                yPain: {
                    type: "linear",
                    position: "right",
                    min: 0,
                    max: 10,
                    ticks: { stepSize: 2 },
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: "Pain Scale (1-10)" }
                },
                x: {
                    ticks: { maxRotation: 45, minRotation: 0 }
                }
            },
            plugins: {
                legend: { position: "top" }
            }
        }
    });
}

// Render Daily Breakdown Table
function renderDailyTable(dailyData) {
    if (!dailyData || dailyData.length === 0) {
        dailyTableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No entries recorded in selected window.</td></tr>';
        return;
    }

    // Sort descending by date for the table
    const sorted = [...dailyData].reverse();
    dailyTableBody.innerHTML = sorted.map(row => {
        let bloodText = '<span class="text-muted">None</span>';
        if (row.blood_events.some > 0 || row.blood_events.alot > 0) {
            const parts = [];
            if (row.blood_events.some > 0) parts.push(`<span class="badge badge-blood-some">${row.blood_events.some} trace</span>`);
            if (row.blood_events.alot > 0) parts.push(`<span class="badge badge-blood-alot">${row.blood_events.alot} a lot</span>`);
            bloodText = parts.join(" ");
        }

        return `
            <tr>
                <td><strong>${row.date}</strong></td>
                <td>${row.count}</td>
                <td>${getBristolBadge(row.avg_bristol)}</td>
                <td>${row.avg_pain !== null ? `${row.avg_pain} / 10` : '--'}</td>
                <td>${row.max_pain !== null ? `${row.max_pain} / 10` : '--'}</td>
                <td>${bloodText}</td>
            </tr>
        `;
    }).join("");
}

// Render Recent Intake Table
function renderRecentTable(logs) {
    if (!logs || logs.length === 0) {
        recentTableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No recent logs recorded yet.</td></tr>';
        return;
    }

    recentTableBody.innerHTML = logs.map(log => `
        <tr>
            <td>${formatDateTime(log.timestamp)}</td>
            <td>${getBristolBadge(log.bristol)}</td>
            <td><strong>${log.pain}</strong> / 10</td>
            <td>${getBloodBadge(log.blood)}</td>
            <td>${log.notes ? `<span>${escapeHtml(log.notes)}</span>` : '<span class="text-muted">-</span>'}</td>
            <td>
                <button class="btn btn-sm btn-danger-outline" onclick="deleteLogEntry(${log.id})">Delete</button>
            </td>
        </tr>
    `).join("");
}

// HTML Escaping Helper
function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[tag] || tag));
}

// Delete Log Entry
window.deleteLogEntry = async function(id) {
    if (!confirm("Are you sure you want to delete this log entry?")) return;
    try {
        const res = await fetch(`/api/logs/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Log entry deleted");
            loadDashboard();
        } else {
            showToast("Failed to delete log entry");
        }
    } catch (err) {
        console.error("Delete failed:", err);
        showToast("Error deleting entry");
    }
};

// Modal Interaction
function openModal() {
    logModal.classList.add("active");
}

function closeModal() {
    logModal.classList.remove("active");
}

// Bristol Selector Buttons
bristolSelector.querySelectorAll(".btn-select").forEach(btn => {
    btn.addEventListener("click", () => {
        bristolSelector.querySelectorAll(".btn-select").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const val = parseInt(btn.dataset.val, 10);
        bristolInput.value = val;
        
        let badgeClass = "badge-normal";
        if (val <= 2) badgeClass = "badge-constipated";
        else if (val >= 5) badgeClass = "badge-diarrhea";
        
        bristolValueDisplay.className = `badge ${badgeClass}`;
        bristolValueDisplay.textContent = BRISTOL_DESCRIPTIONS[val];
    });
});

// Pain Slider
painRange.addEventListener("input", (e) => {
    painValueDisplay.textContent = e.target.value;
});

// Blood Radio Pills
bloodSelector.querySelectorAll(".radio-pill").forEach(pill => {
    pill.addEventListener("click", () => {
        bloodSelector.querySelectorAll(".radio-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        pill.querySelector("input").checked = true;
    });
});

// Form Submission
logForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const bristol = parseInt(bristolInput.value, 10);
    const pain = parseInt(painRange.value, 10);
    const blood = document.querySelector('input[name="blood"]:checked').value;
    const notes = document.getElementById("notesInput").value.trim();

    try {
        const res = await fetch("/api/log", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bristol, pain, blood, notes })
        });

        if (res.ok) {
            const data = await res.json();
            showToast(data.message || "Movement logged successfully!");
            closeModal();
            logForm.reset();
            // Reset to defaults
            bristolSelector.querySelector('[data-val="4"]').click();
            painRange.value = 1;
            painValueDisplay.textContent = "1";
            bloodSelector.querySelector('input[value="none"]').parentElement.click();
            loadDashboard();
        } else {
            const err = await res.json();
            showToast(err.detail || "Failed to log movement");
        }
    } catch (err) {
        console.error("Submission failed:", err);
        showToast("Error communicating with server");
    }
});

// Event Listeners
openLogModalBtn.addEventListener("click", openModal);
closeLogModalBtn.addEventListener("click", closeModal);
cancelModalBtn.addEventListener("click", closeModal);
logModal.addEventListener("click", (e) => {
    if (e.target === logModal) closeModal();
});

timeRangeSelect.addEventListener("change", loadDashboard);
printReportBtn.addEventListener("click", () => {
    window.print();
});

// Initial Load
document.addEventListener("DOMContentLoaded", () => {
    loadDashboard();
});
