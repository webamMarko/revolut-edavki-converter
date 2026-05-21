/**
 * Empty State Components
 *
 * Consistent empty states across all dashboard sections.
 * Usage: renderEmptyState(containerId, sectionName, message)
 */

(function(window) {
    'use strict';

    /**
     * Section-specific icons and messages
     */
    const sectionConfig = {
        summary: {
            icon: '📊',
            title: 'No Portfolio Data',
            message: 'Import your transaction history to see portfolio summary and analytics.'
        },
        tax: {
            icon: '📄',
            title: 'No Tax Data',
            message: 'Import your trades to calculate capital gains and generate tax reports.'
        },
        analytics: {
            icon: '📈',
            title: 'No Analytics Data',
            message: 'Import transactions and sync prices to view performance analytics.'
        },
        charts: {
            icon: '📉',
            title: 'No Chart Data',
            message: 'Import your portfolio to visualize performance over time.'
        },
        projections: {
            icon: '🎯',
            title: 'No Projection Data',
            message: 'Import holdings and set goals to see portfolio projections.'
        },
        dividends: {
            icon: '💰',
            title: 'No Dividend Data',
            message: 'Import transactions to track dividend income and projections.'
        },
        report: {
            icon: '📋',
            title: 'No Report Data',
            message: 'Import your portfolio to generate comprehensive reports.'
        },
        holdings: {
            icon: '💼',
            title: 'No Holdings',
            message: 'Import transactions to see your current positions.'
        },
        default: {
            icon: '📦',
            title: 'No Data',
            message: 'Import your transaction history to get started.'
        }
    };

    /**
     * Render empty state for a section
     * @param {string} containerId - ID of the container element
     * @param {string} sectionName - Section identifier (summary, tax, analytics, etc.)
     * @param {string} customMessage - Optional custom message (overrides default)
     */
    function renderEmptyState(containerId, sectionName, customMessage) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.warn(`Empty state container not found: ${containerId}`);
            return;
        }

        const config = sectionConfig[sectionName] || sectionConfig.default;
        const message = customMessage || config.message;

        container.innerHTML = `
            <div class="empty-state-card">
                <div class="empty-state-icon">${config.icon}</div>
                <h3 class="empty-state-title">${config.title}</h3>
                <p class="empty-state-message">${message}</p>
                <div class="empty-state-actions">
                    <a href="/import" class="btn-primary">
                        <span>📥</span> Import CSV
                    </a>
                    ${getSectionRole() !== 'guest' ? `
                        <button class="btn-secondary" onclick="toggleDemoData()">
                            <span>👁️</span> Try Demo Data
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    /**
     * Get current user role (from global window.ROLE if available)
     */
    function getSectionRole() {
        return window.ROLE || 'guest';
    }

    /**
     * Toggle demo data view (for premium/admin users)
     */
    window.toggleDemoData = function() {
        fetch('/api/demo-toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ demo: true })
        })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                showToast('Switched to demo data. Refresh to see demo portfolio.', 'success');
                setTimeout(() => window.location.reload(), 1000);
            }
        })
        .catch(err => {
            console.error('Demo toggle error:', err);
            showToast('Failed to toggle demo data.', 'error');
        });
    };

    /**
     * Switch back to user's own portfolio
     */
    window.switchToMyPortfolio = function() {
        fetch('/api/demo-toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ demo: false })
        })
        .then(res => res.json())
        .then(data => {
            if (data.ok) {
                showToast('Switched to your portfolio.', 'success');
                setTimeout(() => window.location.reload(), 1000);
            }
        })
        .catch(err => {
            console.error('Demo toggle error:', err);
            showToast('Failed to switch portfolio.', 'error');
        });
    };

    // Export to window
    window.renderEmptyState = renderEmptyState;

})(window);
