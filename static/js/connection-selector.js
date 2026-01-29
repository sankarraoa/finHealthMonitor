/**
 * Connection Selector Component
 * Provides a compact, progressive disclosure UI for selecting connections
 */

class ConnectionSelector {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            allowMultiple: options.allowMultiple !== false, // Default to true
            categories: options.categories || {},
            connections: options.connections || [],
            selectedConnections: options.selectedConnections || [],
            onSelectionChange: options.onSelectionChange || null,
            ...options
        };
        this.selectedConnections = new Set(this.options.selectedConnections.map(c => c.id || c));
        this.init();
    }

    init() {
        if (!this.container) return;
        
        // Group connections by category
        this.groupedConnections = this.groupConnectionsByCategory();
        
        // Render the component
        this.render();
        
        // Attach event listeners
        this.attachEventListeners();
    }

    groupConnectionsByCategory() {
        const grouped = {};
        
        this.options.connections.forEach(conn => {
            const category = conn.category || 'finance';
            if (!grouped[category]) {
                grouped[category] = [];
            }
            grouped[category].push(conn);
        });
        
        return grouped;
    }

    render() {
        const selectedCount = this.selectedConnections.size;
        const selectedConnectionsList = this.getSelectedConnections();
        
        // Build trigger button
        let triggerText = 'Select Connections';
        if (selectedCount === 1) {
            const conn = selectedConnectionsList[0];
            triggerText = `${this.getConnectionDisplayName(conn)}`;
        } else if (selectedCount > 1) {
            triggerText = `${selectedCount} connections`;
        }

        const triggerHTML = `
            <div class="connection-selector-trigger" id="connection-trigger">
                <span class="selected-count">${selectedCount}</span>
                <span class="trigger-text">${triggerText}</span>
                <span class="trigger-icon">▼</span>
            </div>
        `;

        // Build panel
        const panelHTML = `
            <div class="connection-selector-panel" id="connection-panel">
                <div class="connection-selector-header">
                    <h4>Select Connections</h4>
                    <div class="connection-selector-actions">
                        <button class="btn-clear" onclick="connectionSelector.clearSelection()">Clear</button>
                        <button class="btn-apply" onclick="connectionSelector.applySelection()">Apply</button>
                    </div>
                </div>
                <div class="connection-selector-content" id="connection-content">
                    ${this.renderConnectionGroups()}
                </div>
                ${selectedCount > 0 ? this.renderSelectedBadges(selectedConnectionsList) : ''}
            </div>
        `;

        this.container.innerHTML = triggerHTML + panelHTML;
    }

    renderConnectionGroups() {
        let html = '';
        
        // Iterate through categories in order
        const categoryOrder = ['finance', 'hrms', 'crm'];
        const categories = Object.keys(this.groupedConnections).sort((a, b) => {
            const aIndex = categoryOrder.indexOf(a);
            const bIndex = categoryOrder.indexOf(b);
            if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
            if (aIndex === -1) return 1;
            if (bIndex === -1) return -1;
            return aIndex - bIndex;
        });

        categories.forEach(category => {
            const connections = this.groupedConnections[category];
            const categoryName = this.options.categories[category]?.name || category.charAt(0).toUpperCase() + category.slice(1);
            
            html += `
                <div class="connection-category-group">
                    <div class="connection-category-title">${categoryName}</div>
                    ${connections.map(conn => this.renderConnectionItem(conn)).join('')}
                </div>
            `;
        });

        return html;
    }

    renderConnectionItem(conn) {
        const isSelected = this.selectedConnections.has(conn.id);
        const icon = this.getConnectionIcon(conn);
        const displayName = this.getConnectionDisplayName(conn);
        const tenantInfo = this.getTenantInfo(conn);

        return `
            <div class="connection-item" data-connection-id="${conn.id}">
                <input type="${this.options.allowMultiple ? 'checkbox' : 'radio'}" 
                       id="conn-${conn.id}" 
                       ${isSelected ? 'checked' : ''}
                       name="${this.options.allowMultiple ? 'connections' : 'connection'}">
                <label class="connection-item-label" for="conn-${conn.id}">
                    <span class="connection-item-icon">${icon}</span>
                    <span class="connection-item-name">${displayName}</span>
                    ${tenantInfo ? `<span class="connection-item-tenant">${tenantInfo}</span>` : ''}
                </label>
            </div>
        `;
    }

    renderSelectedBadges(selectedConnections) {
        if (!this.options.allowMultiple) return '';
        
        const badges = selectedConnections.map(conn => {
            const displayName = this.getConnectionDisplayName(conn);
            return `
                <div class="connection-badge">
                    <span>${displayName}</span>
                    <span class="badge-remove" onclick="connectionSelector.removeConnection('${conn.id}')">×</span>
                </div>
            `;
        }).join('');

        return `
            <div class="connection-selected-badges">
                ${badges}
            </div>
        `;
    }

    getConnectionIcon(conn) {
        const software = conn.software || '';
        const icons = {
            'xero': '🏦',
            'quickbooks': '📊',
            'bamboohr': '👥',
            'workday': '💼',
            'salesforce': '☁️',
            'hubspot': '🎯'
        };
        return icons[software.toLowerCase()] || '🔗';
    }

    getConnectionDisplayName(conn) {
        return conn.name || 'Unnamed Connection';
    }

    getTenantInfo(conn) {
        if (conn.tenants && conn.tenants.length > 0) {
            if (conn.tenants.length === 1) {
                return conn.tenants[0].tenant_name || '';
            }
            return `${conn.tenants.length} tenants`;
        }
        return null;
    }

    attachEventListeners() {
        const trigger = document.getElementById('connection-trigger');
        const panel = document.getElementById('connection-panel');
        
        if (trigger) {
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                this.togglePanel();
            });
        }

        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (panel && !panel.contains(e.target) && !trigger.contains(e.target)) {
                this.closePanel();
            }
        });

        // Handle connection selection changes
        const content = document.getElementById('connection-content');
        if (content) {
            content.addEventListener('change', (e) => {
                if (e.target.type === 'checkbox' || e.target.type === 'radio') {
                    this.handleConnectionToggle(e.target);
                }
            });
        }
    }

    togglePanel() {
        const panel = document.getElementById('connection-panel');
        const trigger = document.getElementById('connection-trigger');
        
        if (panel && trigger) {
            const isOpen = panel.classList.contains('show');
            if (isOpen) {
                this.closePanel();
            } else {
                this.openPanel();
            }
        }
    }

    openPanel() {
        const panel = document.getElementById('connection-panel');
        const trigger = document.getElementById('connection-trigger');
        
        if (panel && trigger) {
            panel.classList.add('show');
            trigger.classList.add('open');
        }
    }

    closePanel() {
        const panel = document.getElementById('connection-panel');
        const trigger = document.getElementById('connection-trigger');
        
        if (panel && trigger) {
            panel.classList.remove('show');
            trigger.classList.remove('open');
        }
    }

    handleConnectionToggle(checkbox) {
        const connectionId = checkbox.closest('.connection-item').dataset.connectionId;
        
        if (this.options.allowMultiple) {
            if (checkbox.checked) {
                this.selectedConnections.add(connectionId);
            } else {
                this.selectedConnections.delete(connectionId);
            }
        } else {
            // Single selection mode
            this.selectedConnections.clear();
            if (checkbox.checked) {
                this.selectedConnections.add(connectionId);
                // Uncheck other radio buttons
                document.querySelectorAll('input[name="connection"]').forEach(input => {
                    if (input.id !== checkbox.id) {
                        input.checked = false;
                    }
                });
            }
        }
        
        // Update badges
        this.updateSelectedBadges();
    }

    updateSelectedBadges() {
        const panel = document.getElementById('connection-panel');
        if (!panel) return;
        
        const badgesContainer = panel.querySelector('.connection-selected-badges');
        const selectedConnectionsList = this.getSelectedConnections();
        
        if (selectedConnectionsList.length > 0 && this.options.allowMultiple) {
            if (badgesContainer) {
                badgesContainer.outerHTML = this.renderSelectedBadges(selectedConnectionsList);
            } else {
                panel.insertAdjacentHTML('beforeend', this.renderSelectedBadges(selectedConnectionsList));
            }
        } else if (badgesContainer) {
            badgesContainer.remove();
        }
    }

    clearSelection() {
        this.selectedConnections.clear();
        document.querySelectorAll('#connection-content input[type="checkbox"], #connection-content input[type="radio"]').forEach(input => {
            input.checked = false;
        });
        this.updateSelectedBadges();
    }

    removeConnection(connectionId) {
        this.selectedConnections.delete(connectionId);
        const checkbox = document.getElementById(`conn-${connectionId}`);
        if (checkbox) {
            checkbox.checked = false;
        }
        this.updateSelectedBadges();
    }

    applySelection() {
        const selectedConnectionsList = this.getSelectedConnections();
        
        if (this.options.onSelectionChange) {
            this.options.onSelectionChange(selectedConnectionsList);
        }
        
        // Update trigger text
        this.updateTriggerText(selectedConnectionsList);
        
        // Close panel
        this.closePanel();
    }

    updateTriggerText(selectedConnectionsList) {
        const trigger = document.getElementById('connection-trigger');
        const triggerText = trigger.querySelector('.trigger-text');
        const selectedCount = trigger.querySelector('.selected-count');
        
        if (!trigger || !triggerText || !selectedCount) return;
        
        const count = selectedConnectionsList.length;
        selectedCount.textContent = count;
        
        if (count === 0) {
            triggerText.textContent = 'Select Connections';
        } else if (count === 1) {
            triggerText.textContent = this.getConnectionDisplayName(selectedConnectionsList[0]);
        } else {
            triggerText.textContent = `${count} connections`;
        }
    }

    getSelectedConnections() {
        return this.options.connections.filter(conn => 
            this.selectedConnections.has(conn.id)
        );
    }

    getSelectedConnectionIds() {
        return Array.from(this.selectedConnections);
    }
}

// Global instance (will be initialized per page)
let connectionSelector = null;
