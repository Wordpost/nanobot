import { API } from './api.js';
import { UI } from './ui.js';

export class ConfigEditor {
    constructor() {
        this.config = null;
        
        // Modal references
        this.modal = document.getElementById('config-modal');
        this.navContainer = document.getElementById('config-nav');
        this.contentContainer = document.getElementById('config-content');
        this.saveBtn = document.getElementById('config-save-btn');
        this.cancelBtn = document.getElementById('config-cancel-btn');
        
        // Triggers
        this.triggerBtn = document.getElementById('open-config-btn');
        
        if (this.triggerBtn) {
            this.triggerBtn.addEventListener('click', () => this.open());
        }
        
        if (this.cancelBtn) {
            this.cancelBtn.addEventListener('click', () => this.close());
        }
        
        if (this.saveBtn) {
            this.saveBtn.addEventListener('click', () => this.save());
        }
        
        this.activeSection = null;
    }

    async open() {
        this.modal.classList.add('open');
        await this.load();

        // Re-fetch on agent selector change
        const selector = document.getElementById('config-agent-selector-select');
        if (selector && !selector._configBound) {
            selector._configBound = true;
            selector.addEventListener('change', () => this.load());
        }
    }

    async load() {
        try {
            this.saveBtn.textContent = "Loading...";
            this.saveBtn.disabled = true;

            const agent = UI.getSelectedAgent('config-agent-selector');
            this.config = await API.fetchConfigManager(agent);
            this.render();

            this.saveBtn.textContent = "Save Configuration";
            this.saveBtn.disabled = !this.config.message; // disabled if show placeholder msg
        } catch (err) {
            console.error(err);
            this.contentContainer.innerHTML = `<div class="config-selection-required"><p>Error: ${err.message}</p></div>`;
            this.saveBtn.disabled = true;
        } finally {
            if (!this.config?.message) {
                this.saveBtn.disabled = false;
            }
        }
    }

    close() {
        this.modal.classList.remove('open');
    }

    render() {
        this.navContainer.innerHTML = '';
        this.contentContainer.innerHTML = '';

        if (this.config.message) {
            this.contentContainer.innerHTML = `
                <div class="config-selection-required">
                    <div class="config-selection-icon">⚙️</div>
                    <p>${this.config.message}</p>
                </div>
            `;
            this.saveBtn.style.display = 'none';
            return;
        }

        this.saveBtn.style.display = 'block';
        // Define desired top-level sections
        const sections = Object.keys(this.config);
        
        sections.forEach((sectionKey, index) => {
            const val = this.config[sectionKey];
            // Only process top-level objects as sections
            if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
                this.createSection(sectionKey, val, index === 0);
            }
        });
    }

    createSection(sectionKey, sectionData, isActive) {
        // Nav Item
        const navItem = document.createElement('div');
        navItem.className = 'config-nav-item' + (isActive ? ' active' : '');
        navItem.textContent = sectionKey.charAt(0).toUpperCase() + sectionKey.slice(1);
        
        // Content Section
        const contentDiv = document.createElement('div');
        contentDiv.className = 'config-section' + (isActive ? ' active' : '');
        contentDiv.id = `config-section-${sectionKey}`;
        
        const title = document.createElement('h3');
        title.className = 'config-section-title';
        title.textContent = navItem.textContent;
        contentDiv.appendChild(title);
        
        const desc = document.createElement('p');
        desc.className = 'config-section-desc';
        desc.textContent = `Configure ${sectionKey} parameters.`;
        contentDiv.appendChild(desc);
        
        // Grid context
        const grid = document.createElement('div');
        grid.className = 'config-grid';
        
        // Separate top-level primitives from complex nested objects
        const primitives = {};
        const objects = {};
        
        for (const [k, v] of Object.entries(sectionData)) {
            if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
                objects[k] = v;
            } else {
                primitives[k] = v;
            }
        }
        
        // Render a 'General Settings' card if there are root primitives
        if (Object.keys(primitives).length > 0) {
            const card = this.createCard(sectionKey === 'defaults' ? 'Default Parameters' : 'General Settings', primitives, [sectionKey]);
            grid.appendChild(card);
        }
        
        // Render specific tiles for nested objects (e.g., telegram, discord, n8n)
        for (const [cardKey, cardData] of Object.entries(objects)) {
            const card = this.createCard(cardKey, cardData, [sectionKey, cardKey]);
            grid.appendChild(card);
        }
        
        contentDiv.appendChild(grid);
        
        this.navContainer.appendChild(navItem);
        this.contentContainer.appendChild(contentDiv);
        
        // Interaction
        navItem.addEventListener('click', () => {
            document.querySelectorAll('.config-nav-item').forEach(i => i.classList.remove('active'));
            document.querySelectorAll('.config-section').forEach(s => s.classList.remove('active'));
            navItem.classList.add('active');
            contentDiv.classList.add('active');
        });
    }

    createCard(title, data, pathArray) {
        const card = document.createElement('div');
        card.className = 'config-card';
        
        const header = document.createElement('div');
        header.className = 'config-card-header';
        
        const titleEl = document.createElement('div');
        titleEl.className = 'config-card-title';
        titleEl.textContent = title;
        header.appendChild(titleEl);
        
        // Handle standalone `enabled` properly at the root of a card
        if ('enabled' in data) {
            const toggleWrapper = this.createToggle('enabled', data.enabled, [...pathArray, 'enabled']);
            header.appendChild(toggleWrapper);
        }
        
        card.appendChild(header);
        
        const body = document.createElement('div');
        body.className = 'config-card-body';
        
        this.renderFields(data, pathArray, body, ['enabled']); // skip string 'enabled' inside body
        
        // Add Button to generic cards
        const addBtn = this.createAddButton(pathArray, body);
        body.appendChild(addBtn);
        
        card.appendChild(body);
        return card;
    }

    createAddButton(pathArray, parentElement) {
        const addBtn = document.createElement('button');
        addBtn.className = 'config-btn-add';
        addBtn.style.marginTop = '8px';
        addBtn.innerHTML = '+ Add Field';
        addBtn.onclick = () => {
            const key = prompt(`Adding to "${pathArray.join('.')}". Enter new key name:`);
            if (!key) return;
            const rawVal = prompt('Enter JSON value (e.g. true, 12, {"command":"uvx"} or "text"):', '""');
            if (rawVal === null) return;
            let finalVal;
            try {
                finalVal = JSON.parse(rawVal);
            } catch(e) {
                finalVal = rawVal;
            }
            
            const tmp = document.createElement('div');
            this.renderFields({[key]: finalVal}, pathArray, tmp);
            while(tmp.firstChild) {
                parentElement.insertBefore(tmp.firstChild, addBtn);
            }
        };
        return addBtn;
    }

    createToggle(keyName, currentValue, pathArray) {
        const label = document.createElement('label');
        label.className = 'toggle-switch';
        
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = !!currentValue;
        input.dataset.path = pathArray.join('.');
        input.dataset.type = 'boolean';
        
        const slider = document.createElement('span');
        slider.className = 'toggle-slider';
        
        label.appendChild(input);
        label.appendChild(slider);
        return label;
    }

    renderFields(data, currentPathArray, parentElement, skipKeys = []) {
        for (const [k, v] of Object.entries(data)) {
            if (skipKeys.includes(k)) continue;
            
            const newPath = [...currentPathArray, k];
            const field = document.createElement('div');
            field.className = 'config-field';
            
            const fieldLabel = document.createElement('label');
            fieldLabel.textContent = k;
            field.appendChild(fieldLabel);
            
            if (typeof v === 'boolean') {
                const switchWrap = document.createElement('div');
                switchWrap.appendChild(this.createToggle(k, v, newPath));
                field.appendChild(switchWrap);
            } else if (Array.isArray(v)) {
                // simple CSV text input for arrays (like allowFrom)
                const input = document.createElement('input');
                input.type = 'text';
                input.value = v.join(', ');
                input.dataset.path = newPath.join('.');
                input.dataset.type = 'array';
                field.appendChild(input);
            } else if (typeof v === 'object' && v !== null) {
                // Nested object recursion
                const nestedBox = document.createElement('div');
                nestedBox.style.paddingLeft = '12px';
                nestedBox.style.borderLeft = '1px solid var(--border-default)';
                nestedBox.style.marginTop = '8px';
                this.renderFields(v, newPath, nestedBox);
                
                // Add ability to add deep properties
                const nestAddBtn = this.createAddButton(newPath, nestedBox);
                nestedBox.appendChild(nestAddBtn);
                
                field.appendChild(nestedBox);
            } else {
                // string, number, null
                const isMultiLine = typeof v === 'string' && (v.includes('\n') || k.toLowerCase().includes('template') || v.length > 80);
                
                const input = document.createElement(isMultiLine ? 'textarea' : 'input');
                if (!isMultiLine) {
                    input.type = typeof v === 'number' ? 'number' : 'text';
                    if (k.toLowerCase().includes('token') || k.toLowerCase().includes('secret') || k.toLowerCase().includes('password')) {
                        input.type = 'password';
                    }
                } else {
                    // Auto-adjust textarea rows safely
                    input.rows = Math.max(3, Math.min(15, (v.match(/\n/g) || []).length + 2));
                    // Basic styling directly inline or via CSS
                    input.style.resize = 'vertical';
                    input.style.lineHeight = '1.4';
                }
                
                input.value = v === null ? '' : v;
                input.dataset.path = newPath.join('.');
                input.dataset.type = typeof v;
                
                field.appendChild(input);
            }
            
            parentElement.appendChild(field);
        }
    }

    async save() {
        try {
            this.saveBtn.textContent = 'Saving...';
            this.saveBtn.disabled = true;
            
            // Build the new payload by structurally cloning the original to preserve uneditable keys
            const newConfig = JSON.parse(JSON.stringify(this.config));
            
            // query all elements with dataset.path
            const inputs = this.modal.querySelectorAll('[data-path]');
            inputs.forEach(input => {
                const parts = input.dataset.path.split('.');
                let current = newConfig;
                for (let i = 0; i < parts.length - 1; i++) {
                    if (!current[parts[i]]) current[parts[i]] = {};
                    current = current[parts[i]];
                }
                
                const key = parts[parts.length - 1];
                let val;
                
                if (input.dataset.type === 'boolean') {
                    val = input.checked;
                } else if (input.dataset.type === 'number') {
                    val = input.value === '' ? null : Number(input.value);
                } else if (input.dataset.type === 'array') {
                    val = input.value.split(',').map(s => s.trim()).filter(s => s !== '');
                } else {
                    val = input.value === '' && input.dataset.type === 'object' ? null : input.value;
                }
                
                current[key] = val;
            });
            
            const agent = UI.getSelectedAgent('config-agent-selector');
            await API.saveConfigManager(newConfig, agent);
            
            this.saveBtn.textContent = 'Saved!';
            this.config = newConfig; // update local representation
            setTimeout(() => {
                // optionally close
                this.close();
                this.saveBtn.textContent = 'Save Configuration';
                this.saveBtn.disabled = false;
            }, 800);
            
        } catch (err) {
            console.error(err);
            alert("Error saving: " + err.message);
            this.saveBtn.textContent = 'Save Configuration';
            this.saveBtn.disabled = false;
        }
    }
}
