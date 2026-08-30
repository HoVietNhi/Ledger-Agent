const scanButton =
    document.getElementById("scanButton");

const toast =
    document.getElementById("toast");

const actionModal =
    document.getElementById("actionModal");

const dismissActionButton =
    document.getElementById("dismissActionButton");

const approveActionButton =
    document.getElementById("approveActionButton");

const actionModalTitle =
    document.getElementById("actionModalTitle");

const actionModalDescription =
    document.getElementById("actionModalDescription");

const actionCurrentCost =
    document.getElementById("actionCurrentCost");

const actionEstimatedImpact =
    document.getElementById("actionEstimatedImpact");

const alertsPanel =
    document.getElementById("alertsPanel");

const activeAlertCount =
    document.getElementById("activeAlertCount");

const activeAlertNote =
    document.getElementById("activeAlertNote");

const monitoringHero =
    document.getElementById("monitoringHero");

const monitorStatusBadge =
    document.getElementById("monitorStatusBadge");

const lastChecked =
    document.getElementById("lastChecked");

const monitorInterval =
    document.getElementById("monitorInterval");

const gmailSourceStatus =
    document.getElementById("gmailSourceStatus");

const transactionSourceStatus =
    document.getElementById("transactionSourceStatus");

const commitmentList =
    document.getElementById("commitmentList");

const commitmentCount =
    document.getElementById("commitmentCount");


let currentPreparedAction = null;


/* -----------------------------
   TOAST
----------------------------- */

let toastTimer = null;

function showToast(message, duration = 2500) {

    toast.textContent = message;
    toast.classList.add("show");

    if (toastTimer) {
        clearTimeout(toastTimer);
    }

    toastTimer = setTimeout(() => {

        toast.classList.remove("show");

        toastTimer = null;

    }, duration);
}


/* -----------------------------
   ALERT SUMMARY
----------------------------- */

function updateAlertSummary() {

    const activeAlerts =
        alertsPanel.querySelectorAll(
            ".alert-card"
        );

    const count =
        activeAlerts.length;

    activeAlertCount.textContent =
        count;

    if (count === 0) {

        activeAlertNote.textContent =
            "No active alerts";

        activeAlertNote.classList.remove(
            "warning"
        );

    } else {

        activeAlertNote.textContent =
            `${count} meaningful ${
                count === 1
                    ? "change"
                    : "changes"
            }`;

        activeAlertNote.classList.add(
            "warning"
        );
    }
}


/* -----------------------------
   EMPTY ALERT STATE
----------------------------- */

function showEmptyAlertState() {

    const existingEmptyState =
        alertsPanel.querySelector(
            ".alert-empty-state"
        );

    if (existingEmptyState) {
        return;
    }

    const emptyState =
        document.createElement("div");

    emptyState.className =
        "alert-empty-state";

    emptyState.innerHTML = `
        <div class="alert-empty-icon">
            ✓
        </div>

        <h3>Everything looks normal</h3>

        <p>
            No financial changes need your attention right now.
            Safe Signal is still monitoring in the background.
        </p>
    `;

    alertsPanel.appendChild(
        emptyState
    );
}


/* -----------------------------
   RESOLVE ANY ALERT
----------------------------- */

function resolveAlert(eventKey) {

    if (!eventKey) {
        return;
    }

    const alertCards =
        alertsPanel.querySelectorAll(
            ".alert-card"
        );

    const alertCard =
        Array.from(alertCards).find(
            (card) =>
                card.dataset.eventKey
                === eventKey
        );

    if (!alertCard) {
        return;
    }

    alertCard.classList.add(
        "removing"
    );

    setTimeout(() => {

        alertCard.remove();

        updateAlertSummary();
loadMonitorStatus();
loadCommitments();
loadNotifications().catch(
    (error) => console.error(
        "Notification load error:",
        error
    )
);

        const remainingAlerts =
            alertsPanel.querySelectorAll(
                ".alert-card"
            );

        if (
            remainingAlerts.length === 0
        ) {

            showEmptyAlertState();
        }

    }, 400);
}


/* -----------------------------
   MONITOR STATUS
----------------------------- */

const API_BASE =
    (
        ["127.0.0.1", "localhost"].includes(
            window.location.hostname
        )
        && window.location.port === "5500"
    )
        ? "http://127.0.0.1:8001"
        : "";


function formatRelativeTime(isoTimestamp) {

    if (!isoTimestamp) {
        return "Never checked";
    }

    const checked =
        new Date(isoTimestamp);

    const seconds =
        Math.max(
            0,
            Math.floor(
                (Date.now() - checked.getTime())
                / 1000
            )
        );

    if (seconds < 60) {
        return "Checked just now";
    }

    const minutes =
        Math.floor(seconds / 60);

    if (minutes < 60) {
        return `Checked ${minutes} min ago`;
    }

    const hours =
        Math.floor(minutes / 60);

    return `Checked ${hours} hr ago`;
}


async function loadMonitorStatus(
    showFeedback = false
) {

    monitorStatusBadge.textContent =
        "CHECKING";

    scanButton.disabled = true;
    scanButton.textContent = "Refreshing...";

    try {

        const response = await fetch(
            `${API_BASE}/api/monitor/status`
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data = await response.json();

        const status =
            data.status || "unknown";

        monitorStatusBadge.textContent =
            status.toUpperCase();

        monitorStatusBadge.dataset.status =
            status;

        monitoringHero.dataset.status =
            status;

        lastChecked.textContent =
            data.last_checked_at
                ? formatRelativeTime(
                    data.last_checked_at
                )
                : "Last checked: unavailable";

        monitorInterval.textContent =
            `Checks every ${
                data.check_interval_minutes || 15
            } minutes`;

        gmailSourceStatus.textContent =
            "Gmail";

        transactionSourceStatus.textContent =
            "Transactions";

        if (showFeedback) {
            showToast(
                "Monitoring status refreshed."
            );
        }

    } catch (error) {

        monitorStatusBadge.textContent =
            "UNAVAILABLE";

        monitorStatusBadge.dataset.status =
            "error";

        monitoringHero.dataset.status =
            "error";

        lastChecked.textContent =
            "Monitoring status unavailable";

        if (showFeedback) {
            showToast(
                "Could not reach Safe Signal API."
            );
        }

        console.error(
            "Monitor status error:",
            error
        );

    } finally {

        scanButton.disabled = false;
        scanButton.textContent = "Refresh";
    }
}


scanButton.addEventListener(
    "click",
    () => loadMonitorStatus(true)
);


/* -----------------------------
   COMMITMENTS
----------------------------- */

function formatCommitmentDate(value) {
    if (!value) {
        return "Not scheduled";
    }

    return new Date(
        `${value}T00:00:00`
    ).toLocaleDateString(
        "en-CA",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
        }
    );
}


function formatLifecycleState(status) {

    const states = {
        active: {
            label: "Monitoring",
            tone: "active",
        },
        waiting_for_user: {
            label: "Needs decision",
            tone: "attention",
        },
        cancellation_requested: {
            label: "Cancellation requested",
            tone: "pending",
        },
        inactive: {
            label: "Inactive",
            tone: "inactive",
        },
    };

    return (
        states[status]
        || {
            label: (
                status || "Unknown"
            ).replaceAll("_", " "),
            tone: "unknown",
        }
    );
}


let allCommitments = [];
let currentCommitmentFilter = "all";


function getNextAgentAction(item) {

    const status =
        item.status || "active";

    const type =
        item.commitment_type || "";

    if (status === "waiting_for_user") {
        return "Waiting for your decision";
    }

    if (status === "cancellation_requested") {
        return "Verify that the provider actually ends the subscription";
    }

    if (status === "inactive") {
        return "No action needed ? cancellation confirmed";
    }

    if (type === "renewal") {
        return "Watch the renewal date and surface it before the charge";
    }

    return "Check the next charge against the expected amount";
}


function updateCommitmentSummary(items) {

    const total =
        document.getElementById(
            "subscriptionTotal"
        );

    const attention =
        document.getElementById(
            "subscriptionAttention"
        );

    const followup =
        document.getElementById(
            "subscriptionFollowup"
        );

    if (total) {
        total.textContent =
            items.length;
    }

    if (attention) {
        attention.textContent =
            items.filter(
                item =>
                    item.status
                    === "waiting_for_user"
            ).length;
    }

    if (followup) {
        followup.textContent =
            items.filter(
                item =>
                    item.status
                    === "cancellation_requested"
            ).length;
    }
}


function filterCommitments(items) {

    if (
        currentCommitmentFilter
        === "monitoring"
    ) {
        return items.filter(
            item =>
                (item.status || "active")
                === "active"
        );
    }

    if (
        currentCommitmentFilter
        === "attention"
    ) {
        return items.filter(
            item =>
                item.status
                === "waiting_for_user"
        );
    }

    if (
        currentCommitmentFilter
        === "followup"
    ) {
        return items.filter(
            item =>
                item.status
                === "cancellation_requested"
        );
    }

    return items;
}


function formatDisplayLabel(value) {

    const labels = {
        subscription: "Subscription",
        renewal: "Renewal",
        monthly: "Monthly",
        annual: "Annual",
        gmail: "Gmail",
        transaction: "Transactions",
        transactions: "Transactions",
        plaid: "Plaid",
    };

    const key =
        String(value || "")
            .toLowerCase();

    return (
        labels[key]
        || String(value || "Unknown")
            .replaceAll("_", " ")
    );
}


function renderCommitments(items) {

    if (!items.length) {

        commitmentList.innerHTML = `
            <div class="subscription-empty">
                <div class="empty-icon">?</div>

                <h3>
                    Nothing in this view
                </h3>

                <p>
                    Safe Signal will place subscriptions
                    here when they match this lifecycle state.
                </p>
            </div>
        `;

        return;
    }

    commitmentList.innerHTML =
        items.map((item) => {

            const provider =
                item.provider
                || item.merchant
                || "Unknown";

            const initial =
                provider
                    .charAt(0)
                    .toUpperCase();

            const type =
                item.commitment_type
                || "subscription";

            const frequency =
                item.frequency
                || "unscheduled";

            const amount =
                item.expected_amount ?? 0;

            const observedAmount =
                item.observed_amount
                ?? item.expected_amount
                ?? 0;

            const currency =
                item.currency || "";

            const status =
                item.status || "active";

            const lifecycle =
                formatLifecycleState(
                    status
                );

            const source =
                item.source || "unknown";

            const nextAction =
                getNextAgentAction(item);

            const amountChanged =
                Number(observedAmount)
                !== Number(amount);

            return `
                <article
                    class="commitment-card subscription-lifecycle-card"
                    data-subscription-status="${status}"
                >

                    <div class="subscription-card-top">

                        <div class="commitment-main">

                            <div class="service-icon">
                                ${initial}
                            </div>

                            <div>
                                <strong class="commitment-provider">
                                    ${provider}
                                </strong>

                                <div class="commitment-meta">
                                    ${formatDisplayLabel(type)} &middot; ${formatDisplayLabel(frequency)}
                                </div>
                            </div>

                        </div>


                        <span
                            class="commitment-status"
                            data-status="${status}"
                            data-tone="${lifecycle.tone}"
                        >
                            <span class="lifecycle-dot"></span>
                            ${lifecycle.label}
                        </span>

                    </div>


                    <div class="subscription-money-row">

                        <div>
                            <small>
                                Expected
                            </small>

                            <strong class="subscription-amount">
                                ${currency}
                                ${Number(amount).toFixed(2)}
                            </strong>

                            <span>
                                / ${frequency}
                            </span>
                        </div>

                        ${
                            amountChanged
                                ? `
                                <div class="observed-change">
                                    <small>
                                        Latest observed
                                    </small>

                                    <strong>
                                        ${currency}
                                        ${Number(
                                            observedAmount
                                        ).toFixed(2)}
                                    </strong>
                                </div>
                                `
                                : ""
                        }

                    </div>


                    <div class="subscription-info-grid">

                        <div>
                            <small>
                                Next expected
                            </small>

                            <strong>
                                ${formatCommitmentDate(
                                    item.next_expected_date
                                )}
                            </strong>
                        </div>

                        <div>
                            <small>
                                Learned from
                            </small>

                            <strong>
                                ${formatDisplayLabel(source)}
                            </strong>
                        </div>

                    </div>


                    <div class="agent-next-action">

                        <div class="agent-next-icon">
                            ?
                        </div>

                        <div>
                            <small>
                                NEXT AGENT ACTION
                            </small>

                            <strong>
                                ${nextAction}
                            </strong>
                        </div>

                    </div>

                </article>
            `;
        }).join("");
}


function renderFilteredCommitments() {

    renderCommitments(
        filterCommitments(
            allCommitments
        )
    );
}


document
    .querySelectorAll(
        ".subscription-filter"
    )
    .forEach((button) => {

        button.addEventListener(
            "click",
            () => {

                document
                    .querySelectorAll(
                        ".subscription-filter"
                    )
                    .forEach(
                        item =>
                            item.classList.remove(
                                "active"
                            )
                    );

                button.classList.add(
                    "active"
                );

                currentCommitmentFilter =
                    button.dataset
                        .commitmentFilter
                    || "all";

                renderFilteredCommitments();
            }
        );
    });


async function loadCommitments() {

    commitmentList.innerHTML = `
        <div class="commitment-loading is-loading">
            <span
                class="loading-spinner"
                aria-hidden="true"
            ></span>
            Loading commitments…
        </div>
    `;

    try {

        const response = await fetch(
            `${API_BASE}/api/commitments`
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data = await response.json();

        allCommitments =
            data.commitments || [];

        commitmentCount.textContent =
            allCommitments.length;

        updateCommitmentSummary(
            allCommitments
        );

        renderFilteredCommitments();

    } catch (error) {

        commitmentList.innerHTML = `
            <div class="commitment-loading">
                Commitments unavailable.
            </div>
        `;

        console.error(
            "Commitment load error:",
            error
        );
    }
}


/* -----------------------------
   ALERT DECISIONS
----------------------------- */

async function postJson(url) {

    const response = await fetch(
        `${API_BASE}${url}`,
        {
            method: "POST",
        }
    );

    const data = await response.json();

    if (!response.ok || data.success === false) {
        throw new Error(
            data.message
            || data.reason
            || `HTTP ${response.status}`
        );
    }

    return data;
}


async function handleAlertDecision(button) {

    const decision =
        button.dataset.decision;

    const commitmentId =
        button.dataset.commitmentId;

    const notificationId =
        button.dataset.notificationId;

    const originalLabel =
        button.textContent;

    const loadingLabels = {
        keep: "Saving...",
        remind: "Scheduling...",
        cancel: "Preparing...",
    };

    button.disabled = true;
    button.textContent =
        loadingLabels[decision]
        || "Working...";

    try {

        if (decision === "keep") {

            await postJson(
                `/api/commitments/${
                    encodeURIComponent(commitmentId)
                }/keep?notification_id=${
                    encodeURIComponent(notificationId)
                }`
            );

            showToast(
                "Baseline updated. Safe Signal will keep monitoring."
            );

            await loadCommitments();
            await loadNotifications();
            return;
        }


        if (decision === "remind") {

            await postJson(
                `/api/notifications/${
                    encodeURIComponent(notificationId)
                }/remind`
            );

            showToast(
                "Safe Signal will remind you later."
            );

            await loadNotifications();
            return;
        }


        if (decision === "cancel") {

            const data = await postJson(
                `/api/commitments/${
                    encodeURIComponent(commitmentId)
                }/cancel?notification_id=${
                    encodeURIComponent(notificationId)
                }`
            );

            const action =
                data.action || {};

            if (!action.action_id) {
                throw new Error(
                    "Cancellation action was not created."
                );
            }

            currentPreparedAction = {
                actionId: action.action_id,
                commitmentId,
                notificationId,
                merchant:
                    button.dataset.merchant
                    || "this commitment",
            };

            actionModalTitle.textContent =
                `Cancel ${
                    currentPreparedAction.merchant
                }?`;

            actionModalDescription.textContent =
                "Safe Signal prepared the cancellation. Review and approve before execution.";

            actionCurrentCost.textContent =
                button.dataset.currentCost
                || "—";

            actionEstimatedImpact.textContent =
                button.dataset.estimatedImpact
                || "—";

            actionModal.classList.add("show");
        }

    } catch (error) {

        showToast(
            `Action failed: ${error.message}`,
            3500
        );

        console.error(
            "Decision error:",
            error
        );

    } finally {

        if (button.isConnected) {
            button.disabled = false;
            button.textContent =
                originalLabel;
        }
    }
}


alertsPanel.addEventListener(
    "click",
    (event) => {

        const button =
            event.target.closest(
                "[data-decision]"
            );

        if (!button) {
            return;
        }

        handleAlertDecision(button);
    }
);


/* -----------------------------
   NOTIFICATIONS
----------------------------- */

function renderNotifications(items) {

    alertsPanel
        .querySelectorAll(
            ".alert-card, .alert-empty-state, .alert-loading-state"
        )
        .forEach(
            (element) => element.remove()
        );

    if (!items.length) {
        showEmptyAlertState();
        updateAlertSummary();
        return;
    }

    items.forEach((item) => {

        const card =
            document.createElement("article");

        card.className =
            "alert-card lifecycle-attention";

        card.dataset.eventKey =
            item.event_key || "";

        card.dataset.lifecycle =
            item.status || "waiting_for_user";

        const commitmentId =
            item.commitment_id || "";

        const notificationId =
            item.notification_id || "";

        const provider =
            item.title || "Financial change";

        const priority =
            item.priority || "MEDIUM";

        card.innerHTML = `
            <div class="alert-top">
                <div class="service-icon">
                    ${provider.charAt(0).toUpperCase()}
                </div>

                <div>
                    <h3>${provider}</h3>
                    <p>${item.message || ""}</p>
                </div>

                <span class="badge medium alert-badge">
                    ${priority}
                </span>
            </div>

            <div class="decision-actions">

                ${
                    commitmentId
                        ? `
                        <button
                            class="secondary-button"
                            data-decision="keep"
                            data-commitment-id="${commitmentId}"
                            data-notification-id="${notificationId}"
                        >
                            Keep
                        </button>

                        <button
                            class="danger-button"
                            data-decision="cancel"
                            data-commitment-id="${commitmentId}"
                            data-notification-id="${notificationId}"
                            data-merchant="${provider}"
                        >
                            Cancel
                        </button>
                        `
                        : ""
                }

                <button
                    class="text-button"
                    data-decision="remind"
                    data-notification-id="${notificationId}"
                >
                    Remind later
                </button>

            </div>
        `;

        alertsPanel.appendChild(card);
    });

    updateAlertSummary();
}


async function loadNotifications() {

    alertsPanel
        .querySelectorAll(
            ".alert-card, .alert-empty-state, .alert-loading-state"
        )
        .forEach(
            (element) => element.remove()
        );

    const loadingState =
        document.createElement("div");

    loadingState.className =
        "alert-loading-state";

    loadingState.innerHTML = `
        <span
            class="loading-spinner"
            aria-hidden="true"
        ></span>
        Checking for financial changes…
    `;

    alertsPanel.appendChild(
        loadingState
    );

    try {

        const response = await fetch(
            `${API_BASE}/api/notifications`
        );

        if (!response.ok) {
            throw new Error(
                `HTTP ${response.status}`
            );
        }

        const data = await response.json();

        renderNotifications(
            data.notifications || []
        );

    } catch (error) {

        const errorState =
            document.createElement("div");

        errorState.className =
            "alert-error-state";

        errorState.innerHTML = `
            <strong>Could not load financial alerts</strong>
            <p>
                Safe Signal could not reach the API.
                Try refreshing in a moment.
            </p>
        `;

        alertsPanel.appendChild(
            errorState
        );

        activeAlertCount.textContent = "—";
        activeAlertNote.textContent =
            "Alerts unavailable";

        console.error(
            "Notification load error:",
            error
        );

    } finally {

        if (loadingState.isConnected) {
            loadingState.remove();
        }
    }
}


/* -----------------------------
   ACTION MODAL
----------------------------- */

dismissActionButton.addEventListener(
    "click",
    () => {

        actionModal.classList.remove(
            "show"
        );

        currentPreparedAction = null;
    }
);


approveActionButton.addEventListener(
    "click",
    async () => {

        if (!currentPreparedAction) {
            return;
        }

        const action =
            currentPreparedAction;

        approveActionButton.disabled = true;
        approveActionButton.textContent =
            "Executing...";

        try {

            await postJson(
                `/api/actions/${
                    encodeURIComponent(action.actionId)
                }/approve`
            );

            await postJson(
                `/api/actions/${
                    encodeURIComponent(action.actionId)
                }/execute`
            );

            actionModal.classList.remove(
                "show"
            );

            showToast(
                `${action.merchant} cancellation submitted successfully.`,
                3000
            );

            currentPreparedAction = null;

            await loadCommitments();
            await loadNotifications();

        } catch (error) {

            showToast(
                `Cancellation failed: ${error.message}`,
                3500
            );

        } finally {

            approveActionButton.disabled =
                false;

            approveActionButton.textContent =
                "Approve action";
        }
    }
);


/* -----------------------------
   CLICK OUTSIDE MODAL
----------------------------- */

actionModal.addEventListener(
    "click",
    (event) => {

        if (
            event.target
            === actionModal
        ) {

            actionModal.classList.remove(
                "show"
            );

            currentActionButton =
                null;
        }
    }
);


/* -----------------------------
   SIDEBAR VIEW SWITCHING
----------------------------- */

const navButtons =
    document.querySelectorAll(
        ".nav-item[data-target]"
    );

const viewElements =
    document.querySelectorAll(
        "[data-view]"
    );


function targetToView(targetId) {

    const map = {
        overviewSection: "overview",
        alertsPanel: "alerts",
        subscriptionsPanel: "commitments",
        financialInboxPanel: "inbox",
        actionsPanel: "actions",
    };

    return map[targetId] || "overview";
}


function switchView(viewName) {

    viewElements.forEach(
        (element) => {

            const views =
                (
                    element.dataset.view || ""
                ).split(/\s+/);

            element.classList.toggle(
                "view-hidden",
                !views.includes(viewName)
            );
        }
    );

    document.body.dataset.currentView =
        viewName;

    window.scrollTo({
        top: 0,
        behavior: "smooth",
    });
}


navButtons.forEach(
    (button) => {

        button.addEventListener(
            "click",
            () => {

                navButtons.forEach(
                    (item) =>
                        item.classList.remove(
                            "active"
                        )
                );

                button.classList.add(
                    "active"
                );

                switchView(
                    targetToView(
                        button.dataset.target
                    )
                );
            }
        );
    }
);



/* -----------------------------
   HERO ACTION SHORTCUTS
----------------------------- */

const reviewNextActionButton =
    document.getElementById(
        "reviewNextActionButton"
    );

const remindNextActionButton =
    document.getElementById(
        "remindNextActionButton"
    );


if (reviewNextActionButton) {

    reviewNextActionButton.addEventListener(
        "click",
        () => {

            const subscriptionsNav =
                document.querySelector(
                    '.nav-item[data-target="subscriptionsPanel"]'
                );

            if (subscriptionsNav) {
                subscriptionsNav.click();
            }
        }
    );
}


if (remindNextActionButton) {

    remindNextActionButton.addEventListener(
        "click",
        () => {

            const attentionNav =
                document.querySelector(
                    '.nav-item[data-target="alertsPanel"]'
                );

            if (attentionNav) {
                attentionNav.click();
            }
        }
    );
}


/* INITIAL STATE */

switchView("overview");

updateAlertSummary();

loadMonitorStatus();
loadCommitments();

loadNotifications().catch(
    (error) => console.error(
        "Notification load error:",
        error
    )
);

/* ===== FIT METRIC VALUE TO SINGLE LINE ===== */

function fitMetricText(el) {
    if (!el) return;

    const parent = el.parentElement;
    if (!parent) return;

    const maxSize = 54;
    const minSize = 28;

    el.style.whiteSpace = "nowrap";
    el.style.fontSize = "";
    el.style.lineHeight = "0.95";

    let size = maxSize;
    el.style.fontSize = size + "px";

    while (el.scrollWidth > el.clientWidth && size > minSize) {
        size -= 1;
        el.style.fontSize = size + "px";
    }
}

function runMetricFit() {
    document.querySelectorAll("[data-fit-text]").forEach((el) => {
        fitMetricText(el);
    });
}

window.addEventListener("load", runMetricFit);
window.addEventListener("resize", runMetricFit);

if ("ResizeObserver" in window) {
    const metricObserver = new ResizeObserver(() => {
        runMetricFit();
    });

    document.querySelectorAll("[data-fit-text]").forEach((el) => {
        metricObserver.observe(el);
        if (el.parentElement) {
            metricObserver.observe(el.parentElement);
        }
    });
}