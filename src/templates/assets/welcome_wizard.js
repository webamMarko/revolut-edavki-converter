/**
 * Welcome Wizard
 *
 * 4-step onboarding wizard for new premium users.
 * Steps: Welcome → Import → Sync → Celebration
 */

(function(window) {
    'use strict';

    let currentStep = 1;
    let wizardContainer = null;

    /**
     * Initialize and show the welcome wizard
     */
    function showWelcomeWizard() {
        // Check if wizard should be shown
        fetch('/api/onboarding-status')
            .then(res => res.json())
            .then(status => {
                // Auto-complete if user already has data
                if (status.hasData && !status.completed) {
                    markOnboardingComplete();
                    return;
                }

                // Show wizard if not completed
                if (!status.completed) {
                    // Check localStorage for resumed state
                    const savedStep = localStorage.getItem('wizard_step');
                    if (savedStep) {
                        currentStep = parseInt(savedStep, 10);
                        localStorage.removeItem('wizard_step');
                    }

                    createWizard();
                    renderStep(currentStep);
                }
            })
            .catch(err => console.error('Failed to check onboarding status:', err));
    }

    /**
     * Create wizard DOM structure
     */
    function createWizard() {
        if (wizardContainer) return;

        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'wizard-overlay';
        overlay.id = 'welcomeWizard';

        // Create modal
        wizardContainer = document.createElement('div');
        wizardContainer.className = 'wizard-modal';

        overlay.appendChild(wizardContainer);
        document.body.appendChild(overlay);

        // Prevent body scroll
        document.body.style.overflow = 'hidden';
    }

    /**
     * Render specific wizard step
     */
    function renderStep(step) {
        if (!wizardContainer) return;

        currentStep = step;

        const steps = {
            1: renderWelcomeStep,
            2: renderImportStep,
            3: renderSyncStep,
            4: renderCelebrationStep
        };

        const renderFn = steps[step];
        if (renderFn) {
            renderFn();
        }
    }

    /**
     * Step 1: Welcome
     */
    function renderWelcomeStep() {
        wizardContainer.innerHTML = `
            <div class="wizard-step">
                <div class="wizard-progress">
                    <div class="wizard-progress-bar" style="width: 25%"></div>
                </div>
                <div class="wizard-content">
                    <div class="wizard-icon">🎉</div>
                    <h2 class="wizard-title">Welcome to WealthEagle!</h2>
                    <p class="wizard-description">
                        Your personal portfolio analytics platform. Track stocks, CFDs, crypto,
                        and savings with daily granularity and powerful insights.
                    </p>
                    <ul class="wizard-features">
                        <li>📊 Real-time portfolio analytics</li>
                        <li>📈 Performance tracking & projections</li>
                        <li>💰 Dividend monitoring</li>
                        <li>📄 Slovenian tax reports (eDavki)</li>
                    </ul>
                </div>
                <div class="wizard-actions">
                    <button class="btn-primary wizard-btn-large" onclick="window.welcomeWizard.nextStep()">
                        Get Started →
                    </button>
                    <button class="btn-secondary" onclick="window.welcomeWizard.dismiss()">
                        Skip for now
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Step 2: Import
     */
    function renderImportStep() {
        wizardContainer.innerHTML = `
            <div class="wizard-step">
                <div class="wizard-progress">
                    <div class="wizard-progress-bar" style="width: 50%"></div>
                </div>
                <div class="wizard-content">
                    <div class="wizard-icon">📥</div>
                    <h2 class="wizard-title">Import Your Data</h2>
                    <p class="wizard-description">
                        Upload your Revolut trading CSV to get started. We support stocks,
                        CFDs, crypto, and savings accounts.
                    </p>
                    <div class="wizard-info-box">
                        <strong>Supported formats:</strong>
                        <ul>
                            <li>Revolut Stocks & CFDs</li>
                            <li>Revolut Crypto</li>
                            <li>Revolut Savings</li>
                        </ul>
                    </div>
                </div>
                <div class="wizard-actions">
                    <button class="btn-primary wizard-btn-large" onclick="window.welcomeWizard.goToImport()">
                        Import CSV →
                    </button>
                    <button class="btn-secondary" onclick="window.welcomeWizard.tryDemo()">
                        Try Demo Data
                    </button>
                    <button class="btn-text" onclick="window.welcomeWizard.dismiss()">
                        Skip
                    </button>
                </div>
            </div>
        `;
    }

    /**
     * Step 3: Sync
     */
    function renderSyncStep() {
        wizardContainer.innerHTML = `
            <div class="wizard-step">
                <div class="wizard-progress">
                    <div class="wizard-progress-bar" style="width: 75%"></div>
                </div>
                <div class="wizard-content">
                    <div class="wizard-icon">🔄</div>
                    <h2 class="wizard-title">Sync Prices</h2>
                    <p class="wizard-description">
                        Fetching latest prices from Yahoo Finance for your holdings...
                    </p>
                    <div class="wizard-spinner"></div>
                </div>
            </div>
        `;

        // Trigger sync
        showToast('Syncing prices...', 'info', 5000);

        fetch('/sync', { method: 'POST' })
            .then(res => res.json())
            .then(() => {
                showToast('Prices synced successfully!', 'success');
                setTimeout(() => renderStep(4), 1000);
            })
            .catch(err => {
                console.error('Sync failed:', err);
                showToast('Sync failed. You can retry from the dashboard.', 'warning');
                // Still proceed to celebration
                setTimeout(() => renderStep(4), 2000);
            });
    }

    /**
     * Step 4: Celebration
     */
    function renderCelebrationStep() {
        // Launch confetti
        if (window.launchConfetti) {
            launchConfetti(2500);
        }

        // Fetch portfolio highlights
        fetch('/status')
            .then(res => res.json())
            .then(data => {
                const hasData = data.has_data || false;
                const txCount = data.transaction_count || 0;
                const tickerCount = data.ticker_count || 0;

                wizardContainer.innerHTML = `
                    <div class="wizard-step">
                        <div class="wizard-progress">
                            <div class="wizard-progress-bar" style="width: 100%"></div>
                        </div>
                        <div class="wizard-content">
                            <div class="wizard-icon">🎊</div>
                            <h2 class="wizard-title">You're All Set!</h2>
                            <p class="wizard-description">
                                Your portfolio is ready to explore.
                            </p>
                            ${hasData ? `
                                <div class="wizard-highlights">
                                    <div class="wizard-highlight-card">
                                        <div class="wizard-highlight-value">${txCount}</div>
                                        <div class="wizard-highlight-label">Transactions</div>
                                    </div>
                                    <div class="wizard-highlight-card">
                                        <div class="wizard-highlight-value">${tickerCount}</div>
                                        <div class="wizard-highlight-label">Assets</div>
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                        <div class="wizard-actions">
                            <button class="btn-primary wizard-btn-large" onclick="window.welcomeWizard.complete()">
                                View Dashboard →
                            </button>
                        </div>
                    </div>
                `;
            })
            .catch(() => {
                // Fallback if status fetch fails
                wizardContainer.innerHTML = `
                    <div class="wizard-step">
                        <div class="wizard-progress">
                            <div class="wizard-progress-bar" style="width: 100%"></div>
                        </div>
                        <div class="wizard-content">
                            <div class="wizard-icon">🎊</div>
                            <h2 class="wizard-title">You're All Set!</h2>
                            <p class="wizard-description">
                                Welcome to WealthEagle! Explore your dashboard to see analytics and insights.
                            </p>
                        </div>
                        <div class="wizard-actions">
                            <button class="btn-primary wizard-btn-large" onclick="window.welcomeWizard.complete()">
                                View Dashboard →
                            </button>
                        </div>
                    </div>
                `;
            });
    }

    /**
     * Navigate to next step
     */
    function nextStep() {
        if (currentStep < 4) {
            renderStep(currentStep + 1);
        }
    }

    /**
     * Go to import page (save wizard state)
     */
    function goToImport() {
        localStorage.setItem('wizard_step', '3'); // Resume at sync step
        window.location.href = '/import?onboarding=1';
    }

    /**
     * Try demo data
     */
    function tryDemo() {
        if (window.toggleDemoData) {
            toggleDemoData();
        }
        dismiss();
    }

    /**
     * Complete wizard and mark onboarding done
     */
    function complete() {
        markOnboardingComplete();
        closeWizard();
        window.location.reload();
    }

    /**
     * Dismiss wizard (still marks as complete)
     */
    function dismiss() {
        markOnboardingComplete();
        closeWizard();
    }

    /**
     * Close wizard UI
     */
    function closeWizard() {
        const overlay = document.getElementById('welcomeWizard');
        if (overlay) {
            overlay.remove();
        }
        wizardContainer = null;
        document.body.style.overflow = '';
    }

    /**
     * Mark onboarding as completed on server
     */
    function markOnboardingComplete() {
        fetch('/api/onboarding-complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }).catch(err => console.error('Failed to mark onboarding complete:', err));
    }

    /**
     * Replay wizard (from help menu)
     */
    function replayWizard() {
        currentStep = 1;
        createWizard();
        renderStep(1);
    }

    // Export API
    window.welcomeWizard = {
        show: showWelcomeWizard,
        replay: replayWizard,
        nextStep,
        goToImport,
        tryDemo,
        complete,
        dismiss
    };

    // Auto-show on page load for dashboard
    if (window.location.pathname === '/' && window.ROLE && window.ROLE !== 'guest') {
        document.addEventListener('DOMContentLoaded', showWelcomeWizard);
    }

})(window);
