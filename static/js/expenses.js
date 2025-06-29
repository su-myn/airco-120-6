// Place this in static/js/expenses.js

/**
 * Handles complex calculations and data processing for the expenses page
 */
class ExpensesManager {
    constructor() {
        // Store references to DOM elements
        this.monthFilter = document.getElementById('month-filter');
        this.buildingFilter = document.getElementById('building-filter');
        this.saveBtn = document.getElementById('save-btn');
        // REMOVED: this.exportBtn = document.getElementById('export-btn');
        this.reloadBtn = document.getElementById('reload-btn');
        this.expensesData = document.getElementById('expenses-data');
        this.loadingOverlay = document.querySelector('.loading-overlay');
        this.saveMessage = document.getElementById('save-message');

        // Data state
        this.currentUnits = [];
        this.currentExpenses = {};

        // Initialize
        this.init();
    }

    /**
     * Initialize the expense manager
     */
    init() {
        // Set default month if not set
        if (!this.monthFilter.value) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            this.monthFilter.value = `${year}-${month}`;
        }

        // Set up event listeners
        this.setupEventListeners();

        // Load initial data
        this.loadExpensesData();
    }

    /**
     * Set up all event listeners
     */
    setupEventListeners() {
        this.monthFilter.addEventListener('change', () => this.loadExpensesData());
        this.buildingFilter.addEventListener('change', () => this.filterUnits());
        this.saveBtn.addEventListener('click', () => this.saveExpensesData());
        // REMOVED: this.exportBtn.addEventListener('click', () => this.exportToCsv());
        this.reloadBtn.addEventListener('click', () => this.loadExpensesData());

        // Add the sales from bookings button listener
        const loadSalesBtn = document.getElementById('load-sales-btn');
        if (loadSalesBtn) {
          loadSalesBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadSalesFromBookings(year, month);
          });
        }

        // Add the repair costs from issues button listener
        const loadRepairBtn = document.getElementById('load-repair-btn');
        if (loadRepairBtn) {
          loadRepairBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadRepairCostsFromIssues(year, month);
          });
        }

        // Add the replace costs from issues button listener
        const loadReplaceBtn = document.getElementById('load-replace-btn');
        if (loadReplaceBtn) {
          loadReplaceBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadReplaceCostsFromIssues(year, month);
          });
        }
    }

    /**
     * Load expenses data from the server
     */
    loadExpensesData() {
        this.showLoading(true);

        // Get selected month-year
        const [year, month] = this.monthFilter.value.split('-');

        // Make API request to get expense data
        fetch(`/api/expenses?year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => {
                // Store data
                this.currentUnits = data.units || [];
                this.currentExpenses = data.expenses || {};

                // Add any _formula fields from your server response if available
                for (const unitId in this.currentExpenses) {
                    // Check if there are formula fields in the response
                    for (const field in this.currentExpenses[unitId]) {
                        if (field.endsWith('_formula')) {
                            const baseField = field.replace('_formula', '');
                            // Attach formula data attribute to input when rendering
                            // We'll use this in the renderExpensesTable function
                        }
                    }
                }

                // Render table
                this.renderExpensesTable();

                // Apply any active filters
                this.filterUnits();

                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading expenses data:', error);

                // If API fails, generate empty data for all units
                fetch('/api/get_units')
                    .then(response => response.json())
                    .then(units => {
                        this.currentUnits = units;
                        this.currentExpenses = {};

                        // Render empty table
                        this.renderExpensesTable();

                        // Apply any active filters
                        this.filterUnits();

                        this.showLoading(false);
                    })
                    .catch(err => {
                        console.error('Failed to load units:', err);
                        this.showLoading(false);
                        this.showSaveMessage('Failed to load data. Please try again.', true);
                    });
            });
    }

    /**
     * Render the expenses table with current data
     */
    // Inside the ExpensesManager class
    renderExpensesTable() {
        // Clear table
        this.expensesData.innerHTML = '';

        // Add row for each unit
        this.currentUnits.forEach(unit => {
            const unitId = unit.id;
            const unitExpense = this.currentExpenses[unitId] || {
                sales: '',
                rental: '',
                electricity: '',
                water: '',
                sewage: '',
                internet: '',
                cleaner: '',
                laundry: '',
                supplies: '',
                repair: '',
                replace: '',
                other: ''
            };

            // Calculate net earn
            const netEarn = this.calculateNetEarn(unitExpense);

            // Create row
            const row = document.createElement('tr');
            row.dataset.unitId = unitId;
            row.dataset.building = unit.building || '';

            // Unit column
            const unitCell = document.createElement('td');
            unitCell.className = 'unit-column';
            unitCell.textContent = unit.unit_number;
            row.appendChild(unitCell);

            // Expense columns
            const expenseColumns = [
                'sales', 'rental', 'electricity', 'water', 'sewage',
                'internet', 'cleaner', 'laundry', 'supplies',
                'repair', 'replace', 'other'
            ];

            expenseColumns.forEach(column => {
                const cell = document.createElement('td');
                cell.className = 'editable';

                const input = document.createElement('input');
                input.type = 'text';

                // Format the value to 2 decimal places if it's a number
                let value = unitExpense[column] || '';
                if (value !== '' && !isNaN(parseFloat(value))) {
                    value = parseFloat(value).toFixed(2);
                }

                input.value = value;
                input.dataset.column = column;
                input.dataset.unitId = unitId;

                // Rest of the existing event listeners...
                // The rest of your original code here...
                // Check if there's a stored formula for this field
                const formulaField = `${column}_formula`;
                if (this.currentExpenses[unitId] && this.currentExpenses[unitId][formulaField]) {
                    input.dataset.formula = this.currentExpenses[unitId][formulaField];
                }

                // Auto-calculate on input change
                input.addEventListener('input', (e) => {
                    // Update currentExpenses object
                    if (!this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId] = {};
                    }
                    this.currentExpenses[unitId][column] = e.target.value;

                    // Recalculate net earn
                    this.updateNetEarn(unitId);
                });

                // Add focus event to show formula if exists
                input.addEventListener('focus', function() {
                    // When the cell is focused, show the original formula if it exists
                    if (this.dataset.formula) {
                        // Store the display value (calculated result) as a data attribute
                        this.dataset.displayValue = this.value;

                        // Show the original formula for editing
                        this.value = this.dataset.formula;
                    }
                });

                // Add blur event for formula calculation
                input.addEventListener('blur', (e) => {
                    const value = e.target.value.trim();

                    // Check if it's a formula (starts with =)
                    if (value && value.startsWith('=')) {
                        try {
                            // Store the original formula
                            e.target.dataset.formula = value;

                            // Calculate the result
                            const formulaExpression = value.substring(1); // Remove the = sign

                            // Replace any commas with empty strings before evaluating
                            const result = this.calculateFormula(formulaExpression.replace(/,/g, ''));

                            // Show the calculated result
                            e.target.value = result;

                            // Update the expenses data
                            if (!this.currentExpenses[unitId]) {
                                this.currentExpenses[unitId] = {};
                            }
                            this.currentExpenses[unitId][column] = result;
                            // Also store the formula
                            this.currentExpenses[unitId][`${column}_formula`] = value;

                            // Recalculate net earn
                            this.updateNetEarn(unitId);
                        } catch (error) {
                            // Show error styling
                            e.target.classList.add('calculation-error');
                            setTimeout(() => {
                                e.target.classList.remove('calculation-error');
                            }, 2000);
                        }
                    } else if (value && value.match(/[-+*/()]/)) {
                        // If it contains math operators but doesn't start with =, evaluate it directly
                        try {
                            // Remove any formula data if exists
                            if (e.target.dataset.formula) {
                                delete e.target.dataset.formula;
                            }

                            const result = this.calculateFormula(value.replace(/,/g, ''));
                            e.target.value = result;

                            // Update data
                            if (!this.currentExpenses[unitId]) {
                                this.currentExpenses[unitId] = {};
                            }
                            this.currentExpenses[unitId][column] = result;

                            // Remove formula storage if exists
                            if (this.currentExpenses[unitId][`${column}_formula`]) {
                                delete this.currentExpenses[unitId][`${column}_formula`];
                            }

                            // Recalculate net earn
                            this.updateNetEarn(unitId);
                        } catch (error) {
                            e.target.classList.add('calculation-error');
                            setTimeout(() => {
                                e.target.classList.remove('calculation-error');
                            }, 2000);
                        }
                    }
                });

                cell.appendChild(input);
                row.appendChild(cell);
            });


            // Net earn column with 2 decimal places
            const netEarnCell = document.createElement('td');
            netEarnCell.className = 'net-earn';
            netEarnCell.id = `net-earn-${unitId}`;
            netEarnCell.textContent = parseFloat(netEarn).toFixed(2);
            if (parseFloat(netEarn) < 0) {
                netEarnCell.classList.add('negative');
            } else {
                netEarnCell.classList.add('positive');
            }
            row.appendChild(netEarnCell);

            // Add row to table
            this.expensesData.appendChild(row);
        });
    }

    /**
     * Filter units by building
     */
    filterUnits() {
        const building = this.buildingFilter.value;

        const rows = this.expensesData.querySelectorAll('tr');
        rows.forEach(row => {
            if (building === 'all' || row.dataset.building === building) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }

    /**
     * Calculate net earn for a unit's expenses
     * @param {Object} expense - The expense data object
     * @returns {string} - The calculated net earn as a formatted string
     */
    calculateNetEarn(expense) {
        // Get numeric values, defaulting to 0 if empty or NaN
        const getValue = (value) => {
            if (!value) return 0;

            // If it's a formula (check formula field), use the calculated value
            const num = parseFloat(value.toString().replace(/,/g, ''));
            return isNaN(num) ? 0 : num;
        };

        const sales = getValue(expense.sales);
        const rental = getValue(expense.rental);
        const electricity = getValue(expense.electricity);
        const water = getValue(expense.water);
        const sewage = getValue(expense.sewage);
        const internet = getValue(expense.internet);
        const cleaner = getValue(expense.cleaner);
        const laundry = getValue(expense.laundry);
        const supplies = getValue(expense.supplies);
        const repair = getValue(expense.repair);
        const replace = getValue(expense.replace);
        const other = getValue(expense.other);

        // Calculate net earn
        const netEarn = sales - rental - electricity - water - sewage -
                        internet - cleaner - laundry - supplies -
                        repair - replace - other;

        return netEarn.toFixed(2);
    }

    updateNetEarn(unitId) {
        const expense = this.currentExpenses[unitId] || {};
        const netEarn = this.calculateNetEarn(expense);

        const netEarnCell = document.getElementById(`net-earn-${unitId}`);
        if (netEarnCell) {
            netEarnCell.textContent = parseFloat(netEarn).toFixed(2);

            // Update color
            netEarnCell.classList.remove('positive', 'negative');
            if (parseFloat(netEarn) < 0) {
                netEarnCell.classList.add('negative');
            } else {
                netEarnCell.classList.add('positive');
            }
        }
    }

    /**
     * Save expenses data to the server
     */
    saveExpensesData() {
        this.showLoading(true);

        // Get selected month-year
        const [year, month] = this.monthFilter.value.split('-');

        // Prepare data for saving
        const data = {
            year: year,
            month: month,
            expenses: {}
        };

        // Create a deep copy of the expenses object
        for (const unitId in this.currentExpenses) {
            data.expenses[unitId] = {};

            // Copy each expense field, including formula fields
            for (const field in this.currentExpenses[unitId]) {
                data.expenses[unitId][field] = this.currentExpenses[unitId][field];
            }
        }

        // Make API request to save data
        fetch('/api/expenses', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to save data');
            }
            return response.json();
        })
        .then(result => {
            this.showLoading(false);
            this.showSaveMessage('Data saved successfully');
        })
        .catch(error => {
            console.error('Error saving expenses data:', error);
            this.showLoading(false);
            this.showSaveMessage('Failed to save data. Please try again.', true);
        });
    }

    /**
     * Export expenses data to CSV
     */
    exportToCsv() {
        // Create CSV content
        let csvContent = 'Unit,Sales,Rental,Electricity,Water,Sewage,Internet,Cleaner,Laundry,Supplies,Repair,Replace,Other,Net Earn\n';

        // Add data rows
        const rows = this.expensesData.querySelectorAll('tr');
        rows.forEach(row => {
            // Skip hidden rows (filtered out)
            if (row.style.display === 'none') return;

            const unitId = row.dataset.unitId;
            const unitName = row.querySelector('.unit-column').textContent;
            const expense = this.currentExpenses[unitId] || {};

            // Get values for all columns
            const values = [
                unitName,
                expense.sales || '',
                expense.rental || '',
                expense.electricity || '',
                expense.water || '',
                expense.sewage || '',
                expense.internet || '',
                expense.cleaner || '',
                expense.laundry || '',
                expense.supplies || '',
                expense.repair || '',
                expense.replace || '',
                expense.other || '',
                this.calculateNetEarn(expense)
            ];

            // Add row to CSV
            csvContent += values.map(value => `"${value}"`).join(',') + '\n';
        });

        // Create download link
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `PropertyHub_Expenses_${this.monthFilter.value}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /**
     * Show/hide loading overlay
     * @param {boolean} show - Whether to show or hide the overlay
     */
    showLoading(show) {
        this.loadingOverlay.style.display = show ? 'flex' : 'none';
    }

    /**
     * Show save message
     * @param {string} message - The message to display
     * @param {boolean} isError - Whether this is an error message
     */
    showSaveMessage(message, isError = false) {
        this.saveMessage.textContent = message;
        this.saveMessage.classList.toggle('error', isError);
        this.saveMessage.classList.add('show');

        setTimeout(() => {
            this.saveMessage.classList.remove('show');
        }, 3000);
    }

    /**
     * Helper function to calculate formula values
     * @param {string} expression - The formula expression to calculate
     * @returns {string} - The calculated result formatted as a string
     */
    calculateFormula(expression) {
        if (!expression) return '';

        // Clean up the expression
        let cleanExpression = expression.replace(/\+{2,}/g, '+')
                                 .replace(/\-{2,}/g, '-')
                                 .replace(/\*{2,}/g, '*')
                                 .replace(/\/{2,}/g, '/');

        // Replace mixed operations
        cleanExpression = cleanExpression.replace(/\+\-/g, '-')
                                       .replace(/\-\+/g, '-')
                                       .replace(/\-\-/g, '+');

        // Validate expression
        if (/[^0-9\+\-\*\/\.\(\)\s]/.test(cleanExpression)) {
            throw new Error('Invalid characters in expression');
        }

        // Evaluate and return the formatted result
        try {
            const result = Function(`'use strict'; return (${cleanExpression})`)();
            return parseFloat(result).toFixed(2);
        } catch (e) {
            console.error('Error evaluating formula:', e, expression);
            throw e;
        }
    }

    /**
     * Load sales data from bookings
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadSalesFromBookings(year, month) {
        this.showLoading(true);

        // Make API request to get booking data for sales calculations
        fetch(`/api/bookings/monthly_revenue?year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their sales values from bookings
                for (const unitId in data.revenues) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].sales = data.revenues[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: data.revenues[unitId].toFixed(2),
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: '',
                            replace: '',
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading booking revenues:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load booking revenues. Please try again.', true);
            });
    }

    /**
     * Load repair costs from issues
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadRepairCostsFromIssues(year, month) {
        this.showLoading(true);

        // Make API request to get issue costs for repair calculations
        fetch(`/api/issues/monthly_costs?year=${year}&month=${month}&type=repair`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their repair values from issues
                for (const unitId in data.costs) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].repair = data.costs[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: '',
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: data.costs[unitId].toFixed(2),
                            replace: '',
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading issue repair costs:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load repair costs. Please try again.', true);
            });
    }

    /**
     * Load replacement costs from issues
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadReplaceCostsFromIssues(year, month) {
        this.showLoading(true);

        // Make API request to get issue costs for replacement calculations
        fetch(`/api/issues/monthly_costs?year=${year}&month=${month}&type=replace`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their replace values from issues
                for (const unitId in data.costs) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].replace = data.costs[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: '',
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: '',
                            replace: data.costs[unitId].toFixed(2),
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading issue replacement costs:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load replacement costs. Please try again.', true);
            });
    }
}

// Initialize the expenses manager when the page loads
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('expenses-table')) {
        window.expensesManager = new ExpensesManager();
    }
});

// Initialize Analysis Tab
function initializeAnalysisTab() {
    // Set current month
    const now = new Date();
    const currentMonthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthYearSelect = document.getElementById('analysis-month-year');
    if (monthYearSelect.querySelector(`option[value="${currentMonthYear}"]`)) {
        monthYearSelect.value = currentMonthYear;
    }

    // Set up event listeners
    document.getElementById('analysis-month-year').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'pl-statement') {
            updatePnLStatement();
        } else {
            updateAnalysis();
        }
    });
    document.getElementById('analysis-unit').addEventListener('change', updateAnalysis);

    // Building filter event listener
    document.getElementById('analysis-building')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });

    // Populate the unit dropdown
    populateAnalysisUnits();

    // Initialize the pie chart
    initializeExpenseChart();

    // ADD THIS: Load initial data for the default analysis (expenses breakdown)
    setTimeout(() => {
        updateAnalysis();
    }, 500); // Small delay to ensure dropdowns are populated first
}

// Populate units dropdown for analysis tab
function populateAnalysisUnits() {
    fetch('/api/get_units')
        .then(response => response.json())
        .then(units => {
            const unitSelect = document.getElementById('analysis-unit');

            // Clear existing options except "All Units"
            while (unitSelect.options.length > 1) {
                unitSelect.remove(1);
            }

            // Add units to dropdown
            units.forEach(unit => {
                const option = document.createElement('option');
                option.value = unit.id;
                option.textContent = unit.unit_number;
                unitSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading units:', error);
        });
}

// Run the expense analysis
function runExpenseAnalysis() {
    const month = document.getElementById('analysis-month').value;
    const unitId = document.getElementById('analysis-unit').value;
    const year = document.getElementById('report-year').value; // Use the same year as the report tab

    // Show loading indicator
    document.getElementById('analysis-loading').style.display = 'flex';

    // In a real implementation, you would fetch the data from your API
    // For now, we'll simulate a delay and then show some placeholder content
    setTimeout(() => {
        // Hide loading
        document.getElementById('analysis-loading').style.display = 'none';

        // Display placeholder analysis
        const analysisResults = document.getElementById('analysis-results');
        const monthName = document.getElementById('analysis-month').options[document.getElementById('analysis-month').selectedIndex].text;
        const unitName = document.getElementById('analysis-unit').options[document.getElementById('analysis-unit').selectedIndex].text;

        analysisResults.innerHTML = `
            <h3>Expense Analysis for ${monthName} ${year}</h3>
            <h4>Unit: ${unitName}</h4>

            <div class="analysis-metrics" style="margin-top: 20px;">
                <div class="metric-card" style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                    <h5 style="margin-top: 0;">Revenue vs. Expenses</h5>
                    <div class="metric-content" style="display: flex; justify-content: space-between;">
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #28a745;">RM 3,500</div>
                            <div>Total Revenue</div>
                        </div>
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #dc3545;">RM 2,100</div>
                            <div>Total Expenses</div>
                        </div>
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #17a2b8;">RM 1,400</div>
                            <div>Net Profit</div>
                        </div>
                    </div>
                </div>

                <div class="expense-breakdown" style="margin-top: 20px;">
                    <h5>Expense Breakdown</h5>
                    <div class="breakdown-chart" style="height: 30px; background-color: #e9ecef; border-radius: 4px; overflow: hidden; display: flex;">
                        <div style="width: 35%; height: 100%; background-color: #dc3545;" title="Rental: 35%"></div>
                        <div style="width: 20%; height: 100%; background-color: #fd7e14;" title="Utilities: 20%"></div>
                        <div style="width: 15%; height: 100%; background-color: #ffc107;" title="Maintenance: 15%"></div>
                        <div style="width: 30%; height: 100%; background-color: #6c757d;" title="Others: 30%"></div>
                    </div>
                    <div style="display: flex; margin-top: 10px; flex-wrap: wrap;">
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #dc3545; margin-right: 5px;"></div>
                            <span>Rental (35%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #fd7e14; margin-right: 5px;"></div>
                            <span>Utilities (20%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #ffc107; margin-right: 5px;"></div>
                            <span>Maintenance (15%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #6c757d; margin-right: 5px;"></div>
                            <span>Others (30%)</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }, 1000);
}

// Add Analysis tab initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Existing code...

    // Initialize Analysis Tab
    initializeAnalysisTab();
});

// Initialize the Analysis tab
function initializeAnalysisTab() {
    // Populate the unit dropdown
    populateAnalysisUnits();

    // Set current month
    const now = new Date();
    const currentMonthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthYearSelect = document.getElementById('analysis-month-year');
    if (monthYearSelect.querySelector(`option[value="${currentMonthYear}"]`)) {
        monthYearSelect.value = currentMonthYear;
    }

    // Set up event listeners
    document.getElementById('analysis-month-year').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'pl-statement') {
            updatePnLStatement();
        } else {
            updateAnalysis(); // Your existing function for the expenses breakdown
        }
    });
    document.getElementById('analysis-unit').addEventListener('change', updateAnalysis);
    document.getElementById('refresh-analysis-btn').addEventListener('click', updateAnalysis);

    // Initialize the pie chart
    initializeExpenseChart();

    // Load initial data
    updateAnalysis();
}

// Populate units dropdown for analysis
function populateAnalysisUnits() {
    fetch('/api/get_units')
        .then(response => response.json())
        .then(units => {
            const unitSelect = document.getElementById('analysis-unit');

            // Clear existing options except "All Units"
            while (unitSelect.options.length > 1) {
                unitSelect.remove(1);
            }

            // Add units to dropdown
            units.forEach(unit => {
                const option = document.createElement('option');
                option.value = unit.id;
                option.textContent = unit.unit_number;
                unitSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading units:', error);
        });
}

// Chart instance
let expensePieChart = null;

// Initialize the expense chart
function initializeExpenseChart() {
    const ctx = document.getElementById('expense-pie-chart');

    // First check if there's a chart instance already associated with this canvas
    if (window.expensePieChart instanceof Chart) {
        // Properly destroy the existing chart
        window.expensePieChart.destroy();
    }

    // Create a new chart
    window.expensePieChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#dc3545', // red
                    '#fd7e14', // orange
                    '#ffc107', // yellow
                    '#20c997', // teal
                    '#0dcaf0', // cyan
                    '#6610f2', // indigo
                    '#6f42c1', // purple
                    '#d63384', // pink
                    '#198754', // green
                    '#0d6efd'  // blue
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 15,
                        padding: 15
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: RM ${value.toLocaleString()} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Update the analysis based on selected month and unit
function updateAnalysis() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;
    const selectedBuilding = document.getElementById('analysis-building').value; // Get the building

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Calculate previous month
    let prevYear = year;
    let prevMonth = month - 1;

    if (prevMonth === 0) {
        prevMonth = 12;
        prevYear--;
    }

    // Show loading state
    document.querySelector('.analysis-content').classList.add('loading');

    // Fetch data for current month - include building parameter
    fetch(`/api/expenses?year=${year}&month=${month}&building=${selectedBuilding}`)
        .then(response => response.json())
        .then(currentData => {
            // Process the current month expense data
            const currentExpenseData = processExpenseData(currentData, selectedUnit);

            // Now fetch previous month's data - include building parameter
            fetch(`/api/expenses?year=${prevYear}&month=${prevMonth}&building=${selectedBuilding}`)
                .then(response => response.json())
                .then(prevData => {
                    // Process the previous month expense data
                    const prevExpenseData = processExpenseData(prevData, selectedUnit);

                    // Calculate percentage change
                    const percentChange = calculatePercentChange(
                        prevExpenseData.total,
                        currentExpenseData.total
                    );

                    // Update the UI with the data
                    updateExpenseDisplay(currentExpenseData, percentChange);

                    // Hide loading state
                    document.querySelector('.analysis-content').classList.remove('loading');

                    // Fetch and display top units if needed
                    if (selectedUnit === 'all') {
                        fetchTopExpenseUnits(year, month, selectedBuilding);
                    } else {
                        document.querySelector('.top-units-section').style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('Error fetching previous month data:', error);
                    // Still update the UI with current month data
                    updateExpenseDisplay(currentExpenseData);
                    document.querySelector('.analysis-content').classList.remove('loading');

                    // Fetch and display top units if needed
                    if (selectedUnit === 'all') {
                        fetchTopExpenseUnits(year, month, selectedBuilding);
                    } else {
                        document.querySelector('.top-units-section').style.display = 'none';
                    }
                });
        })
        .catch(error => {
            console.error('Error fetching current month data:', error);
            document.querySelector('.analysis-content').classList.remove('loading');
            document.querySelector('.analysis-content').innerHTML =
                '<p class="error-message">Failed to load expense data. Please try again.</p>';
        });
}


// Helper function to calculate percentage change
function calculatePercentChange(oldValue, newValue) {
    if (oldValue === 0) {
        return newValue > 0 ? 100 : 0; // If old value was 0, and new value > 0, then it's a 100% increase
    }

    return ((newValue - oldValue) / oldValue) * 100;
}


// Process real expense data
function processExpenseData(apiData, unitId) {
    const units = apiData.units || [];
    const expenses = apiData.expenses || {};

    // Filter to just the selected unit if specified
    let filteredUnits = units;
    if (unitId !== 'all') {
        filteredUnits = units.filter(unit => unit.id == unitId);
    }

    // Initialize categories with all expense types
    const categories = [
        { name: 'Rental', amount: 0 },
        { name: 'Electricity', amount: 0 },
        { name: 'Water', amount: 0 },
        { name: 'Sewage', amount: 0 },
        { name: 'Internet', amount: 0 },
        { name: 'Cleaner', amount: 0 },
        { name: 'Laundry', amount: 0 },
        { name: 'Supplies', amount: 0 },
        { name: 'Repair', amount: 0 },
        { name: 'Replace', amount: 0 },
        { name: 'Other', amount: 0 }
    ];

    // Calculate totals by expense category
    let total = 0;

    filteredUnits.forEach(unit => {
        const unitExpenses = expenses[unit.id] || {};

        // Add each expense type to the appropriate category
        if (unitExpenses.rental) categories.find(c => c.name === 'Rental').amount += parseFloat(unitExpenses.rental) || 0;
        if (unitExpenses.electricity) categories.find(c => c.name === 'Electricity').amount += parseFloat(unitExpenses.electricity) || 0;
        if (unitExpenses.water) categories.find(c => c.name === 'Water').amount += parseFloat(unitExpenses.water) || 0;
        if (unitExpenses.sewage) categories.find(c => c.name === 'Sewage').amount += parseFloat(unitExpenses.sewage) || 0;
        if (unitExpenses.internet) categories.find(c => c.name === 'Internet').amount += parseFloat(unitExpenses.internet) || 0;
        if (unitExpenses.cleaner) categories.find(c => c.name === 'Cleaner').amount += parseFloat(unitExpenses.cleaner) || 0;
        if (unitExpenses.laundry) categories.find(c => c.name === 'Laundry').amount += parseFloat(unitExpenses.laundry) || 0;
        if (unitExpenses.supplies) categories.find(c => c.name === 'Supplies').amount += parseFloat(unitExpenses.supplies) || 0;
        if (unitExpenses.repair) categories.find(c => c.name === 'Repair').amount += parseFloat(unitExpenses.repair) || 0;
        if (unitExpenses.replace) categories.find(c => c.name === 'Replace').amount += parseFloat(unitExpenses.replace) || 0;
        if (unitExpenses.other) categories.find(c => c.name === 'Other').amount += parseFloat(unitExpenses.other) || 0;
    });

    // Remove categories with zero amount
    const nonZeroCategories = categories.filter(cat => cat.amount > 0);

    // Calculate total
    total = nonZeroCategories.reduce((sum, category) => sum + category.amount, 0);

    // Calculate percentages
    nonZeroCategories.forEach(category => {
        category.percentage = Math.round((category.amount / total) * 100);
    });

    // Sort by amount (highest to lowest)
    nonZeroCategories.sort((a, b) => b.amount - a.amount);

    // Find top expense
    const topExpense = nonZeroCategories.length > 0 ? nonZeroCategories[0] : { name: 'None', percentage: 0 };

    // Calculate average per unit
    const unitCount = filteredUnits.length;
    const avgPerUnit = unitCount > 0 ? Math.round(total / unitCount) : 0;

    return {
        total: total,
        categories: nonZeroCategories,
        topExpense: topExpense,
        avgPerUnit: avgPerUnit,
        unitCount: unitCount
    };
}

// Get sample expense data (in a real app, you would fetch this from your backend)
function getSampleExpenseData(year, month, unitId) {
    // Sample expense categories with amounts
    const categories = [
        { name: 'Electricity', amount: 24000 },
        { name: 'Water', amount: 2400 },
        { name: 'Sewage', amount: 480 },
        { name: 'Internet', amount: 2400 },
        { name: 'Cleaner', amount: 29400 }
    ];

    // Calculate total
    const total = categories.reduce((sum, category) => sum + category.amount, 0);

    // Calculate percentages
    const data = categories.map(category => {
        return {
            ...category,
            percentage: Math.round((category.amount / total) * 100)
        };
    });

    // Sort by amount (highest to lowest)
    data.sort((a, b) => b.amount - a.amount);

    // Find top expense
    const topExpense = data[0];

    // Calculate average per unit (sample uses 10 units for "all")
    const unitCount = unitId === 'all' ? 10 : 1;
    const avgPerUnit = Math.round(total / unitCount);

    return {
        total,
        categories: data,
        topExpense,
        avgPerUnit,
        unitCount
    };
}

// Update the UI with expense data
// Update the UI with expense data
function updateExpenseDisplay(data, percentChange = null) {
    // Update the metrics cards
    document.getElementById('total-expenses-value').textContent = `RM ${data.total.toLocaleString()}`;

    // Update the percentage change if available
    const expensesChangeElement = document.getElementById('expenses-change');
    if (percentChange !== null) {
        const formattedChange = percentChange.toFixed(1);
        const isPositive = percentChange > 0;

        expensesChangeElement.innerHTML = `
            <span style="color: ${isPositive ? '#dc3545' : '#28a745'}">
                ${isPositive ? '+' : ''}${formattedChange}% vs previous month
            </span>
        `;
    } else {
        expensesChangeElement.innerHTML = '';
    }

    document.getElementById('top-expense-name').textContent = data.topExpense.name;
    document.getElementById('top-expense-amount').textContent = `RM${data.topExpense.amount.toLocaleString()} (${data.topExpense.percentage}%)`;
    document.getElementById('avg-expense-value').textContent = `RM ${data.avgPerUnit.toLocaleString()}`;
    document.getElementById('units-count').textContent = `${data.unitCount} units`;

    // Update the pie chart
    updateExpenseChart(data.categories);

    // Update the summary table
    updateExpenseSummary(data.categories, data.total);
}


// Update the expense pie chart
// Update the expense pie chart
function updateExpenseChart(categories) {
    // Null/undefined check for categories
    if (!categories || !Array.isArray(categories)) {
        console.error("Invalid categories data for expense chart:", categories);
        return; // Exit early if data is invalid
    }

    // Ensure window.expensePieChart exists
    if (!window.expensePieChart) {
        console.warn("Expense pie chart not initialized, initializing now");
        initializeExpenseChart();
    }

    // Safely check and update chart data
    try {
        // Update chart data
        window.expensePieChart.data.labels = categories.map(c => c.name);
        window.expensePieChart.data.datasets[0].data = categories.map(c => c.amount);
        window.expensePieChart.update();
    } catch (error) {
        console.error("Error updating expense chart:", error);
        // Attempt to re-initialize the chart
        initializeExpenseChart();
    }
}

// Update the expense summary table
// Update the expense summary table
function updateExpenseSummary(categories, total) {
    const tbody = document.getElementById('expense-summary-tbody');
    tbody.innerHTML = '';

    // Add a row for each category
    categories.forEach(category => {
        const row = document.createElement('tr');

        // Create cells for category, amount, and percentage
        const categoryCell = document.createElement('td');
        categoryCell.textContent = category.name;

        const amountCell = document.createElement('td');
        // Format with 2 decimal places
        amountCell.textContent = category.amount.toFixed(2);

        const percentageCell = document.createElement('td');
        percentageCell.textContent = `${category.percentage}%`;

        // Add cells to row
        row.appendChild(categoryCell);
        row.appendChild(amountCell);
        row.appendChild(percentageCell);

        // Add row to table
        tbody.appendChild(row);
    });

    // Update total in footer - make sure to format with 2 decimal places
    document.getElementById('summary-total-amount').textContent = total.toFixed(2);
}

// Add Analysis tab initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Existing code...

    // Initialize Analysis Tab
    initializeAnalysisTab();
});

// Function to fetch top expense units
function fetchTopExpenseUnits(year, month, building) {
    // Show the top units section
    document.querySelector('.top-units-section').style.display = 'block';

    // Add building to the query if provided
    const buildingParam = building && building !== 'all' ? `&building=${building}` : '';

    fetch(`/api/expenses?year=${year}&month=${month}${buildingParam}`)
        .then(response => response.json())
        .then(data => {
            const topUnits = calculateTopExpenseUnits(data);
            renderTopUnitsChart(topUnits);
        })
        .catch(error => {
            console.error('Error fetching top units data:', error);
            document.querySelector('.top-units-chart-container').innerHTML =
                '<p class="error-message">Failed to load top units data. Please try again.</p>';
        });
}


// Function to calculate top expense units
function calculateTopExpenseUnits(data) {
    const units = data.units || [];
    const expenses = data.expenses || {};

    // Calculate total expenses for each unit
    const unitExpenses = units.map(unit => {
        const unitData = expenses[unit.id] || {};

        // Sum all expense categories for this unit
        const totalExpense =
            parseFloat(unitData.rental || 0) +
            parseFloat(unitData.electricity || 0) +
            parseFloat(unitData.water || 0) +
            parseFloat(unitData.sewage || 0) +
            parseFloat(unitData.internet || 0) +
            parseFloat(unitData.cleaner || 0) +
            parseFloat(unitData.laundry || 0) +
            parseFloat(unitData.supplies || 0) +
            parseFloat(unitData.repair || 0) +
            parseFloat(unitData.replace || 0) +
            parseFloat(unitData.other || 0);

        return {
            id: unit.id,
            unit_number: unit.unit_number,
            total_expense: totalExpense
        };
    });

    // Filter out units with zero expenses
    const nonZeroUnits = unitExpenses.filter(unit => unit.total_expense > 0);

    // Sort by expense (highest to lowest)
    nonZeroUnits.sort((a, b) => b.total_expense - a.total_expense);

    // Get top 10 (or fewer if less than 10 exist)
    return nonZeroUnits.slice(0, 10);
}


// Function to render the top units chart
function renderTopUnitsChart(topUnits) {
    // Check if chart already exists and destroy it
    if (window.topUnitsChart instanceof Chart) {
        window.topUnitsChart.destroy();
    }

    const ctx = document.getElementById('top-units-chart').getContext('2d');

    // Prepare data for the chart
    const labels = topUnits.map(unit => unit.unit_number);
    const data = topUnits.map(unit => unit.total_expense);

    // Create gradient fill for bars
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(238, 77, 45, 0.8)');
    gradient.addColorStop(1, 'rgba(238, 77, 45, 0.2)');

    // Create the chart
    window.topUnitsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Expenses (RM)',
                data: data,
                backgroundColor: gradient,
                borderColor: 'rgba(238, 77, 45, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return 'RM ' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'RM ' + value;
                        }
                    }
                }
            }
        }
    });
}

// Add this in the existing script section or create a new script tag
document.addEventListener('DOMContentLoaded', function() {
    // Set up the analysis tab switching
    const analysisOptions = document.querySelectorAll('.analysis-option');

    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                updatePnLStatement(); // Call this to load the real data

                // Here you could add code to load/refresh the P&L data if needed
                // updatePnLStatement();
            }
        });
    });
});


// This script fixes the unit selection in the P&L Statement tab

// 1. Fix the updatePnLStatement function to properly handle unit filtering
// Add this at the top of your script section
let pnlUpdateInProgress = false;

function updatePnLStatement() {
    // If an update is already in progress, don't start another one
    if (pnlUpdateInProgress) {
        console.log("P&L update already in progress, skipping this request");
        return;
    }

    // Set the flag to indicate we're updating
    pnlUpdateInProgress = true;

    // Get the current month and year from the filter
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Get selected unit
    const selectedUnit = document.getElementById('analysis-unit').value;
    console.log("Updating P&L statement for unit:", selectedUnit);

    // Define selectedBuilding
    const selectedBuilding = document.getElementById('analysis-building')?.value || 'all';

    // Get previous month for comparison
    let prevYear = year;
    let prevMonth = month - 1;
    if (prevMonth === 0) {
        prevMonth = 12;
        prevYear--;
    }

    // Get previous month name for display
    const monthNames = ["January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"];
    const prevMonthName = monthNames[prevMonth-1]; // Adjust index since array is 0-based

    // Show loading state
    document.querySelector('.pl-statement-content').classList.add('loading');

    // Update the title with unit information
    if (selectedUnit !== 'all') {
        const unitText = document.getElementById('analysis-unit').options[
            document.getElementById('analysis-unit').selectedIndex
        ].text;
        document.getElementById('pl-statement-subtitle').textContent =
            `${monthNames[month-1]} ${year} | Unit: ${unitText}`;
    } else {
        document.getElementById('pl-statement-subtitle').textContent =
            `${monthNames[month-1]} ${year} | All Units`;
    }

    // Add building parameter to fetch URLs if not 'all'
    const buildingParam = selectedBuilding !== 'all' ? `&building=${selectedBuilding}` : '';

    // Fetch data for current month
    fetch(`/api/expenses?year=${year}&month=${month}${buildingParam}`)
        .then(response => response.json())
        .then(data => {
            // Get all units
            const units = data.units || [];
            const expenses = data.expenses || {};

            // Filter units if a specific unit is selected
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            console.log(`Found ${filteredUnits.length} units after filtering`);

            // Calculate totals
            let totalSales = 0;
            let totalRental = 0;
            let totalElectricity = 0;
            let totalWater = 0;
            let totalSewage = 0;
            let totalInternet = 0;
            let totalCleaner = 0;
            let totalLaundry = 0;
            let totalSupplies = 0;
            let totalRepair = 0;
            let totalReplace = 0;
            let totalOther = 0;

            // Process each unit's data
            filteredUnits.forEach(unit => {
                const unitId = unit.id;
                const unitExpenses = expenses[unitId] || {};

                // Sum up sales and expenses
                totalSales += parseFloat(unitExpenses.sales || 0);
                totalRental += parseFloat(unitExpenses.rental || 0);
                totalElectricity += parseFloat(unitExpenses.electricity || 0);
                totalWater += parseFloat(unitExpenses.water || 0);
                totalSewage += parseFloat(unitExpenses.sewage || 0);
                totalInternet += parseFloat(unitExpenses.internet || 0);
                totalCleaner += parseFloat(unitExpenses.cleaner || 0);
                totalLaundry += parseFloat(unitExpenses.laundry || 0);
                totalSupplies += parseFloat(unitExpenses.supplies || 0);
                totalRepair += parseFloat(unitExpenses.repair || 0);
                totalReplace += parseFloat(unitExpenses.replace || 0);
                totalOther += parseFloat(unitExpenses.other || 0);
            });

            // Calculate totals
            const totalRevenue = totalSales;
            const totalExpenses = totalRental + totalElectricity + totalWater + totalSewage +
                                 totalInternet + totalCleaner + totalLaundry + totalSupplies +
                                 totalRepair + totalReplace + totalOther;
            const netIncome = totalRevenue - totalExpenses;

            // Now fetch previous month data for comparison
            fetch(`/api/expenses?year=${prevYear}&month=${prevMonth}${buildingParam}`)
                .then(response => response.json())
                .then(prevData => {
                    // Calculate previous month totals
                    let prevTotalSales = 0;
                    let prevTotalExpenses = 0;

                    const prevUnits = prevData.units || [];
                    const prevExpensesData = prevData.expenses || {};

                    // Filter previous month units if a specific unit is selected
                    const filteredPrevUnits = selectedUnit === 'all' ?
                        prevUnits :
                        prevUnits.filter(unit => unit.id == selectedUnit);

                    // Process each unit's data for previous month
                    filteredPrevUnits.forEach(unit => {
                        const unitId = unit.id;
                        const unitExpenses = prevExpensesData[unitId] || {};

                        // Sum up sales
                        prevTotalSales += parseFloat(unitExpenses.sales || 0);

                        // Sum up all expenses
                        prevTotalExpenses += parseFloat(unitExpenses.rental || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.electricity || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.water || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.sewage || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.internet || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.cleaner || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.laundry || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.supplies || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.repair || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.replace || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.other || 0);
                    });

                    const prevNetIncome = prevTotalSales - prevTotalExpenses;

                    // Calculate percentage changes
                    const revenueChange = prevTotalSales === 0 ? 0 : ((totalRevenue - prevTotalSales) / prevTotalSales) * 100;
                    const expensesChange = prevTotalExpenses === 0 ? 0 : ((totalExpenses - prevTotalExpenses) / prevTotalExpenses) * 100;
                    const incomeChange = prevNetIncome === 0 ? 0 : ((netIncome - prevNetIncome) / prevNetIncome) * 100;

                    // Update summary cards
                    document.getElementById('pl-total-revenue').textContent = new Intl.NumberFormat('en-US', {
                        minimumFractionDigits: 0,
                        maximumFractionDigits: 0
                    }).format(totalRevenue);
                    document.getElementById('pl-revenue-change').textContent = revenueChange.toFixed(1);
                    document.getElementById('pl-revenue-prev-month').textContent = prevMonthName;

                    document.getElementById('pl-total-expenses').textContent = new Intl.NumberFormat('en-US', {
                        minimumFractionDigits: 0,
                        maximumFractionDigits: 0
                    }).format(totalExpenses);
                    document.getElementById('pl-expenses-change').textContent = (expensesChange >= 0 ? '+' + expensesChange.toFixed(1) : expensesChange.toFixed(1));

                    document.getElementById('pl-expenses-prev-month').textContent = prevMonthName;

                    document.getElementById('pl-net-income').textContent = formatNumber(netIncome);
                    document.getElementById('pl-income-change').textContent = (incomeChange >= 0 ? '+' + incomeChange.toFixed(1) : incomeChange.toFixed(1));

                    document.getElementById('pl-income-prev-month').textContent = prevMonthName;

                    // Update table content
                    updatePLTable(
                        totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                        totalInternet, totalCleaner, totalLaundry, totalSupplies,
                        totalRepair, totalReplace, totalOther,
                        totalRevenue, totalExpenses
                    );

                    // Hide loading state
                    document.querySelector('.pl-statement-content').classList.remove('loading');

                    // Reset update flag
                    pnlUpdateInProgress = false;
                })
                .catch(error => {
                    console.error('Error fetching previous month data:', error);
                    // Still update with current month data
                    updatePLTableWithoutComparison(
                        totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                        totalInternet, totalCleaner, totalLaundry, totalSupplies,
                        totalRepair, totalReplace, totalOther,
                        totalRevenue, totalExpenses
                    );
                    document.querySelector('.pl-statement-content').classList.remove('loading');

                    // Reset update flag on error
                    pnlUpdateInProgress = false;
                });
        })
        .catch(error => {
            console.error('Error fetching current month data:', error);
            document.querySelector('.pl-statement-content').classList.remove('loading');
            document.querySelector('.pl-statement-content').innerHTML =
                '<p class="error-message">Failed to load P&L data. Please try again.</p>';

            // Reset update flag on error
            pnlUpdateInProgress = false;
        });
}


// 2. Make sure the event listeners properly handle P&L updates when unit changes
document.addEventListener('DOMContentLoaded', function() {
    // Set up the analysis tab switching and make sure the event listener works for P&L tab
    const analysisOptions = document.querySelectorAll('.analysis-option');

    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
                // Refresh expenses breakdown analysis
                updateAnalysis();
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                // Update P&L statement with current selections
                updatePnLStatement();
            }
        });
    });

    // Ensure the unit selection change handler updates the P&L statement when appropriate
    document.getElementById('analysis-unit').addEventListener('change', function() {
        // Check which analysis is currently active
        const activeAnalysis = document.querySelector('.analysis-option.active')?.getAttribute('data-analysis');

        if (activeAnalysis === 'pl-statement') {
            // Update the P&L statement if that's the active view
            updatePnLStatement();
        } else {
            // Otherwise update the regular analysis
            updateAnalysis();
        }
    });
});

// Helper function to format numbers with commas
function formatNumber(num) {
    return num.toLocaleString('en-US', {maximumFractionDigits: 0});
}

// Function to update the P&L table with real data
// In expenses.js, update the updatePLTable function
function updatePLTable(totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                     totalInternet, totalCleaner, totalLaundry, totalSupplies,
                     totalRepair, totalReplace, totalOther,
                     totalRevenue, totalExpenses) {

    const tableBody = document.getElementById('pl-table-body');
    if (!tableBody) return;

    // Clear existing rows
    tableBody.innerHTML = '';

    // Create income section
    const incomeRow = document.createElement('tr');
    incomeRow.style.backgroundColor = '#f5f7f9';
    incomeRow.innerHTML = `
        <td style="padding: 12px 15px; font-weight: bold;">Income</td>
        <td></td>
        <td></td>
        <td></td>
    `;
    tableBody.appendChild(incomeRow);

    // Add sales row
    const salesRow = document.createElement('tr');
    const salesPercentage = (totalRevenue > 0) ? ((totalSales / totalRevenue) * 100).toFixed(1) : 0;
    salesRow.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">Sales</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(totalSales)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${salesPercentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: #4CAF50;">${parseFloat(document.getElementById('pl-revenue-change').textContent).toFixed(1)}%</td>
    `;
    tableBody.appendChild(salesRow);

    // Create expenses section - UPDATED TO INCLUDE TOTAL EXPENSES
    const expensesRow = document.createElement('tr');
    expensesRow.style.backgroundColor = '#f5f7f9';
    const expensesPercentage = (totalRevenue > 0) ? ((totalExpenses / totalRevenue) * 100).toFixed(1) : 0;
    expensesRow.innerHTML = `
        <td style="padding: 12px 15px; font-weight: bold;">Expenses</td>
        <td style="padding: 12px 15px; text-align: right; font-weight: bold;">${formatNumber(totalExpenses)}</td>
        <td style="padding: 12px 15px; text-align: right; font-weight: bold;">${expensesPercentage}%</td>
        <td style="padding: 12px 15px; text-align: right; font-weight: bold; color: #FF5722;">${parseFloat(document.getElementById('pl-expenses-change').textContent).toFixed(1)}%</td>
    `;
    tableBody.appendChild(expensesRow);

    // Add expense rows with previous month comparison
    // Fetch the previous month values from the summary cards
    const expensesChangePercent = parseFloat(document.getElementById('pl-expenses-change').textContent);

    // This is a simplified approach since we don't have individual expense category changes
    // In a real implementation, you'd calculate these individually
    addExpenseRowWithComparison(tableBody, 'Rental', totalRental, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Electricity', totalElectricity, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Water', totalWater, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Sewage', totalSewage, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Internet', totalInternet, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Cleaner', totalCleaner, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Laundry', totalLaundry, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Supplies', totalSupplies, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Repair', totalRepair, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Replace', totalReplace, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Other', totalOther, totalExpenses, expensesChangePercent);

    // Add Total row
    const netIncomeChangePercent = parseFloat(document.getElementById('pl-income-change').textContent);
    const netIncome = totalRevenue - totalExpenses;
    const netIncomePercentage = (totalRevenue > 0) ? ((netIncome / totalRevenue) * 100).toFixed(1) : 0;

    const totalRow = document.createElement('tr');
    totalRow.style.backgroundColor = '#e9ecef';
    totalRow.style.fontWeight = 'bold';
    totalRow.innerHTML = `
        <td style="padding: 12px 15px;">Net Income</td>
        <td style="padding: 12px 15px; text-align: right;">${formatNumber(netIncome)}</td>
        <td style="padding: 12px 15px; text-align: right;">${netIncomePercentage}%</td>
        <td style="padding: 12px 15px; text-align: right; color: ${netIncomeChangePercent >= 0 ? '#4CAF50' : '#FF5722'};">${netIncomeChangePercent.toFixed(1)}%</td>
    `;
    tableBody.appendChild(totalRow);
}

// Helper function to format numbers with thousand separators and 2 decimal places
function formatNumber(value) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

// Helper function to add expense rows with comparison data
function addExpenseRowWithComparison(tableBody, label, amount, totalExpenses, changePercent) {
    if (amount <= 0) return; // Skip zero amounts

    const row = document.createElement('tr');
    const percentage = (totalExpenses > 0) ? ((amount / totalExpenses) * 100).toFixed(1) : 0;

    row.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">${label}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(amount)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${percentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: ${changePercent >= 0 ? '#FF5722' : '#4CAF50'};">${changePercent.toFixed(1)}%</td>
    `;

    tableBody.appendChild(row);
}
// Helper function to add expense rows
function addExpenseRow(tableBody, label, amount, totalExpenses) {
    if (amount <= 0) return; // Skip zero amounts

    const row = document.createElement('tr');
    const percentage = (totalExpenses > 0) ? ((amount / totalExpenses) * 100).toFixed(0) : 0;

    row.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">${label}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(amount)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${percentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: #FF5722;"></td>
    `;

    tableBody.appendChild(row);
}


// Initialize YoY comparison data and chart
function initializeYoYComparison() {
    // Set up month-year dropdown event listener
    document.getElementById('analysis-month-year').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'yoy-comparison') {
            updateYoYComparison();
        }
    });

    // Set up unit dropdown event listener
    document.getElementById('analysis-unit').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'yoy-comparison') {
            updateYoYComparison();
        }
    });

    // Initialize the chart
    const ctx = document.getElementById('yoy-trend-chart').getContext('2d');
    window.yoyTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'RM' + value.toLocaleString();
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += 'RM' + context.parsed.y.toLocaleString();
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// Update YoY comparison data and visualization
function updateYoYComparison() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse current year and month
    const [currentYear, currentMonth] = selectedMonthYear.split('-').map(Number);

    // Calculate previous year (same month)
    const previousYear = currentYear - 1;

    // Update title and subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"];
    const monthName = monthNames[currentMonth - 1];

    // Update subtitle based on selected unit
    let unitText = "All Properties";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('yoy-comparison-subtitle').textContent =
        `${monthName} ${currentYear} vs ${monthName} ${previousYear} | ${unitText}`;

    // Show loading state
    document.querySelector('.yoy-comparison-content').classList.add('loading');

    // Fetch data for current year month
    fetchMonthlyDataForYear(currentYear, selectedUnit)
        .then(currentYearData => {
            // Fetch data for previous year
            fetchMonthlyDataForYear(previousYear, selectedUnit)
                .then(previousYearData => {
                    // Update the comparison cards
                    updateYoYComparisonCards(currentYearData, previousYearData, currentMonth);

                    // Update the trend chart
                    updateYoYTrendChart(currentYearData, previousYearData, currentYear, previousYear);

                    // Hide loading state
                    document.querySelector('.yoy-comparison-content').classList.remove('loading');
                })
                .catch(error => {
                    console.error("Error fetching previous year data:", error);
                    document.querySelector('.yoy-comparison-content').classList.remove('loading');
                });
        })
        .catch(error => {
            console.error("Error fetching current year data:", error);
            document.querySelector('.yoy-comparison-content').classList.remove('loading');
        });
}

// Fetch monthly data for a specific year
function fetchMonthlyDataForYear(year, unitId) {
    return new Promise((resolve, reject) => {
        fetch(`/api/expenses/yearly?year=${year}&building=all`)
            .then(response => response.json())
            .then(data => {
                // Process the data
                const processedData = {
                    revenue: {},
                    expenses: {},
                    profit: {}
                };

                // Filter units if specific unit is selected
                let unitsToProcess = data.units;
                if (unitId !== 'all') {
                    unitsToProcess = data.units.filter(unit => unit.id == unitId);
                }

                // Initialize data structures for each month
                for (let month = 1; month <= 12; month++) {
                    processedData.revenue[month] = 0;
                    processedData.expenses[month] = 0;
                    processedData.profit[month] = 0;
                }

                // Process each unit's data
                unitsToProcess.forEach(unit => {
                    const unitId = unit.id;
                    const unitExpenses = data.expenses[unitId] || {};

                    // For each month
                    for (let month = 1; month <= 12; month++) {
                        const monthData = unitExpenses[month] || {};

                        // Revenue (sales)
                        const revenue = parseFloat(monthData.sales || 0);
                        processedData.revenue[month] += revenue;

                        // Calculate total expenses for this unit/month
                        const expenses =
                            parseFloat(monthData.rental || 0) +
                            parseFloat(monthData.electricity || 0) +
                            parseFloat(monthData.water || 0) +
                            parseFloat(monthData.sewage || 0) +
                            parseFloat(monthData.internet || 0) +
                            parseFloat(monthData.cleaner || 0) +
                            parseFloat(monthData.laundry || 0) +
                            parseFloat(monthData.supplies || 0) +
                            parseFloat(monthData.repair || 0) +
                            parseFloat(monthData.replace || 0) +
                            parseFloat(monthData.other || 0);

                        processedData.expenses[month] += expenses;

                        // Calculate profit
                        processedData.profit[month] += (revenue - expenses);
                    }
                });

                resolve(processedData);
            })
            .catch(error => {
                console.error(`Error fetching data for year ${year}:`, error);
                reject(error);
            });
    });
}

// Update the YoY comparison cards with real data
function updateYoYComparisonCards(currentYearData, previousYearData, currentMonth) {
    // Get the current month's data
    const currentRevenue = currentYearData.revenue[currentMonth] || 0;
    const currentExpenses = currentYearData.expenses[currentMonth] || 0;
    const currentProfit = currentYearData.profit[currentMonth] || 0;

    // Get the previous year's same month data
    const previousRevenue = previousYearData.revenue[currentMonth] || 0;
    const previousExpenses = previousYearData.expenses[currentMonth] || 0;
    const previousProfit = previousYearData.profit[currentMonth] || 0;

    // Calculate percentage changes
    let revenueChange = 0;
    if (previousRevenue > 0) {
        revenueChange = ((currentRevenue - previousRevenue) / previousRevenue) * 100;
    }

    let expensesChange = 0;
    if (previousExpenses > 0) {
        expensesChange = ((currentExpenses - previousExpenses) / previousExpenses) * 100;
    }

    let profitChange = 0;
    if (previousProfit > 0) {
        profitChange = ((currentProfit - previousProfit) / previousProfit) * 100;
    }

    // Update the display with formatted numbers
    document.getElementById('yoy-current-revenue').textContent = Math.round(currentRevenue).toLocaleString();
    document.getElementById('yoy-previous-revenue').textContent = Math.round(previousRevenue).toLocaleString();
    document.getElementById('yoy-revenue-change').textContent = (revenueChange >= 0 ? '+' : '') + revenueChange.toFixed(1) + '%';

    document.getElementById('yoy-current-expenses').textContent = Math.round(currentExpenses).toLocaleString();
    document.getElementById('yoy-previous-expenses').textContent = Math.round(previousExpenses).toLocaleString();
    document.getElementById('yoy-expenses-change').textContent = (expensesChange >= 0 ? '+' : '') + expensesChange.toFixed(1) + '%';

    document.getElementById('yoy-current-profit').textContent = Math.round(currentProfit).toLocaleString();
    document.getElementById('yoy-previous-profit').textContent = Math.round(previousProfit).toLocaleString();
    document.getElementById('yoy-profit-change').textContent = (profitChange >= 0 ? '+' : '') + profitChange.toFixed(1) + '%';

    // Set appropriate colors
    document.getElementById('yoy-revenue-change').style.color = (revenueChange >= 0) ? '#4CAF50' : '#F44336';
    document.getElementById('yoy-expenses-change').style.color = (expensesChange >= 0) ? '#F44336' : '#4CAF50';
    document.getElementById('yoy-profit-change').style.color = (profitChange >= 0) ? '#3F51B5' : '#F44336';
}

// Update the YoY trend chart with real data
function updateYoYTrendChart(currentYearData, previousYearData, currentYear, previousYear) {
    // Prepare datasets for the chart
    const datasets = [
        {
            label: currentYear + ' Revenue',
            data: Array.from({length: 12}, (_, i) => Math.round(currentYearData.revenue[i+1] || 0)),
            borderColor: '#4CAF50',
            backgroundColor: 'rgba(76, 175, 80, 0.1)',
            borderWidth: 2,
            fill: false
        },
        {
            label: previousYear + ' Revenue',
            data: Array.from({length: 12}, (_, i) => Math.round(previousYearData.revenue[i+1] || 0)),
            borderColor: '#4CAF50',
            backgroundColor: 'rgba(76, 175, 80, 0.1)',
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false
        },
        {
            label: currentYear + ' Expenses',
            data: Array.from({length: 12}, (_, i) => Math.round(currentYearData.expenses[i+1] || 0)),
            borderColor: '#F44336',
            backgroundColor: 'rgba(244, 67, 54, 0.1)',
            borderWidth: 2,
            fill: false
        },
        {
            label: previousYear + ' Expenses',
            data: Array.from({length: 12}, (_, i) => Math.round(previousYearData.expenses[i+1] || 0)),
            borderColor: '#F44336',
            backgroundColor: 'rgba(244, 67, 54, 0.1)',
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false
        }
    ];

    // Update the chart
    window.yoyTrendChart.data.datasets = datasets;
    window.yoyTrendChart.update();
}

// Add initialization to main document ready function
document.addEventListener('DOMContentLoaded', function() {
    // Existing initialization code...

    // Initialize YoY comparison
    initializeYoYComparison();

    // Modify the event listener for analysis options to include YoY comparison
    const analysisOptions = document.querySelectorAll('.analysis-option');
    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';
            document.querySelector('.yoy-comparison-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
                updateAnalysis(); // Refresh the data
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                updatePnLStatement(); // Refresh the data
            } else if (analysisType === 'yoy-comparison') {
                document.querySelector('.yoy-comparison-content').style.display = 'block';
                updateYoYComparison(); // Load the YoY comparison data
            }
        });
    });
});

// Function to update the ROI Analysis data
function updateROIAnalysis() {
    // Get the selected month and year
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Update the subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];

    let unitText = "All Units";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('roi-analysis-subtitle').textContent = `${monthNames[month-1]} ${year} | ${unitText}`;

    // Show loading state
    document.querySelector('.roi-analysis-content').classList.add('loading');

    // Fetch the data
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            // Process the data
            const units = data.units || [];
            const expenses = data.expenses || {};

            // Filter units based on selection
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            // Clear existing table rows
            const tableBody = document.getElementById('roi-analysis-tbody');
            tableBody.innerHTML = '';

            // Variables for totals
            let totalNetProfit = 0;
            let totalRental = 0;

            // Create a row for each unit
            filteredUnits.forEach(unit => {
                const unitId = unit.id;
                const unitExpense = expenses[unitId] || {};

                // Calculate net profit and get rental value
                const sales = parseFloat(unitExpense.sales || 0);
                const rental = parseFloat(unitExpense.rental || 0);
                const otherExpenses =
                    parseFloat(unitExpense.electricity || 0) +
                    parseFloat(unitExpense.water || 0) +
                    parseFloat(unitExpense.sewage || 0) +
                    parseFloat(unitExpense.internet || 0) +
                    parseFloat(unitExpense.cleaner || 0) +
                    parseFloat(unitExpense.laundry || 0) +
                    parseFloat(unitExpense.supplies || 0) +
                    parseFloat(unitExpense.repair || 0) +
                    parseFloat(unitExpense.replace || 0) +
                    parseFloat(unitExpense.other || 0);

                const netProfit = sales - rental - otherExpenses;

                // Calculate ROI
                let roi = 0;
                if (rental > 0) {
                    roi = (netProfit / rental) * 100;
                }

                // Determine performance category
                let performance = 'Poor';
                let performanceColor = '#dc3545';

                if (roi >= 50) {
                    performance = 'Excellent';
                    performanceColor = '#28a745';
                } else if (roi >= 20) {
                    performance = 'Good';
                    performanceColor = '#007bff';
                } else if (roi >= 5) {
                    performance = 'Average';
                    performanceColor = '#fd7e14';
                }

                // Create table row
                const row = document.createElement('tr');
                row.dataset.netProfit = netProfit;
                row.dataset.rental = rental;
                row.dataset.roi = roi.toFixed(1);
                row.dataset.performance = performance;
                row.innerHTML = `
                    <td style="padding: 12px 15px; text-align: left; border-bottom: 1px solid #f0f0f0;">${unit.unit_number}</td>
                    <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">RM${netProfit.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</td>
                    <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">RM${rental.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</td>
                    <td style="padding: 12px 15px; text-align: center; border-bottom: 1px solid #f0f0f0;">${roi.toFixed(1)}%</td>
                    <td style="padding: 12px 15px; text-align: center; border-bottom: 1px solid #f0f0f0;">
                        <span style="display: inline-block; padding: 4px 12px; background-color: ${performanceColor}; color: white; border-radius: 20px;">${performance}</span>
                    </td>
                `;
                tableBody.appendChild(row);

                // Update totals
                totalNetProfit += netProfit;
                totalRental += rental;
            });

            // Calculate total ROI
            let totalRoi = 0;
            if (totalRental > 0) {
                totalRoi = (totalNetProfit / totalRental) * 100;
            }

            // Determine total performance
            let totalPerformance = 'Poor';
            let totalPerformanceColor = '#dc3545';

            if (totalRoi >= 50) {
                totalPerformance = 'Excellent';
                totalPerformanceColor = '#28a745';
            } else if (totalRoi >= 20) {
                totalPerformance = 'Good';
                totalPerformanceColor = '#007bff';
            } else if (totalRoi >= 5) {
                totalPerformance = 'Average';
                totalPerformanceColor = '#fd7e14';
            }

            // Update footer
            document.getElementById('roi-total-profit').textContent = `RM${totalNetProfit.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}`;
            document.getElementById('roi-total-rental').textContent = `RM${totalRental.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}`;
            document.getElementById('roi-total-percentage').textContent = `${totalRoi.toFixed(1)}%`;
            document.getElementById('roi-total-performance').innerHTML = `
                <span style="display: inline-block; padding: 4px 12px; background-color: ${totalPerformanceColor}; color: white; border-radius: 20px;">
                    ${totalPerformance}
                </span>
            `;

            // Hide loading state
            document.querySelector('.roi-analysis-content').classList.remove('loading');
        })
        .catch(error => {
            console.error('Error fetching expense data for ROI analysis:', error);
            document.querySelector('.roi-analysis-content').classList.remove('loading');
            document.querySelector('.roi-analysis-content').innerHTML = `
                <p class="error-message">Failed to load ROI analysis data. Please try again.</p>
            `;
        });
}

// Modify the existing event listener for analysis options to include ROI Analysis
document.addEventListener('DOMContentLoaded', function() {
    const analysisOptions = document.querySelectorAll('.analysis-option');
    if (analysisOptions.length > 0) {
        analysisOptions.forEach(option => {
            option.addEventListener('click', function() {
                // Remove active class from all options
                analysisOptions.forEach(opt => opt.classList.remove('active'));

                // Add active class to clicked option
                this.classList.add('active');

                // Get the analysis type
                const analysisType = this.getAttribute('data-analysis');

                // Hide all analysis content
                document.querySelector('.analysis-content').style.display = 'none';
                document.querySelector('.pl-statement-content').style.display = 'none';
                document.querySelector('.yoy-comparison-content').style.display = 'none';
                document.querySelector('.roi-analysis-content').style.display = 'none';

                // Show the selected analysis content
                if (analysisType === 'expenses-breakdown') {
                    document.querySelector('.analysis-content').style.display = 'block';
                    updateAnalysis(); // Refresh the data
                } else if (analysisType === 'pl-statement') {
                    document.querySelector('.pl-statement-content').style.display = 'block';
                    updatePnLStatement(); // Refresh the data
                } else if (analysisType === 'yoy-comparison') {
                    document.querySelector('.yoy-comparison-content').style.display = 'block';
                    updateYoYComparison(); // Load the YoY comparison data
                } else if (analysisType === 'roi-analysis') {
                    document.querySelector('.roi-analysis-content').style.display = 'block';
                    updateROIAnalysis(); // Load the ROI analysis data
                }
            });
        });
    }

    // Add event listeners for month and unit selector to update ROI analysis
    document.getElementById('analysis-month-year')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'roi-analysis') {
            updateROIAnalysis();
        }
    });

    document.getElementById('analysis-unit')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'roi-analysis') {
            updateROIAnalysis();
        }
    });

    // Add event listener for building selector
    document.getElementById('analysis-building')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });
});

// Variable to track current sort state
let roiSortConfig = {
    column: null,
    direction: 'asc'
};

// Function to sort the ROI table
function sortROITable(column) {
    const tableBody = document.getElementById('roi-analysis-tbody');
    const rows = Array.from(tableBody.querySelectorAll('tr'));

    // Reset all indicators
    const indicators = document.querySelectorAll('[id^="sort-"][id$="-indicator"]');
    indicators.forEach(indicator => {
        indicator.textContent = '';
    });

    // Update sort configuration
    if (roiSortConfig.column === column) {
        // Toggle direction if same column is clicked
        roiSortConfig.direction = roiSortConfig.direction === 'asc' ? 'desc' : 'asc';
    } else {
        // Set new column and default to ascending
        roiSortConfig.column = column;
        roiSortConfig.direction = 'asc';
    }

    // Set the indicator for the current sort column
    const indicator = document.getElementById(`sort-${column}-indicator`);
    indicator.textContent = roiSortConfig.direction === 'asc' ? ' ▲' : ' ▼';

    // Sort the rows
    rows.sort((a, b) => {
        let valueA, valueB;

        if (column === 'unit') {
            // First cell contains unit name (text)
            valueA = a.cells[0].textContent.trim();
            valueB = b.cells[0].textContent.trim();
            return roiSortConfig.direction === 'asc'
                ? valueA.localeCompare(valueB)
                : valueB.localeCompare(valueA);

        } else if (column === 'profit' || column === 'rental') {
            // Extract numeric value from "RM1,234" format
            const indexMap = { 'profit': 1, 'rental': 2 };
            const cellIndex = indexMap[column];

            valueA = parseFloat(a.cells[cellIndex].textContent.replace(/[^0-9.-]+/g, ''));
            valueB = parseFloat(b.cells[cellIndex].textContent.replace(/[^0-9.-]+/g, ''));

        } else if (column === 'roi') {
            // Extract percentage value
            valueA = parseFloat(a.cells[3].textContent);
            valueB = parseFloat(b.cells[3].textContent);

        } else if (column === 'performance') {
            // Map performance to numeric values for sorting
            const performanceMap = {
                'Excellent': 4,
                'Good': 3,
                'Average': 2,
                'Poor': 1
            };

            const textA = a.cells[4].querySelector('span').textContent.trim();
            const textB = b.cells[4].querySelector('span').textContent.trim();

            valueA = performanceMap[textA] || 0;
            valueB = performanceMap[textB] || 0;
        }

        // For numeric comparisons
        if (column !== 'unit') {
            if (isNaN(valueA)) valueA = 0;
            if (isNaN(valueB)) valueB = 0;

            return roiSortConfig.direction === 'asc'
                ? valueA - valueB
                : valueB - valueA;
        }
    });

    // Reappend rows in the new order
    rows.forEach(row => {
        tableBody.appendChild(row);
    });
}


// Income by Unit Analysis
function initializeIncomeByUnitAnalysis() {
    // Set up chart/table view toggle
    document.getElementById('income-chart-view').addEventListener('click', function() {
        this.classList.add('active');
        document.getElementById('income-table-view').classList.remove('active');
        document.getElementById('income-chart-container').style.display = 'block';
        document.getElementById('income-table-container').style.display = 'none';
    });

    document.getElementById('income-table-view').addEventListener('click', function() {
        this.classList.add('active');
        document.getElementById('income-chart-view').classList.remove('active');
        document.getElementById('income-chart-container').style.display = 'none';
        document.getElementById('income-table-container').style.display = 'block';
    });
}

// Function to update Income by Unit analysis
function updateIncomeByUnitAnalysis() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Update the subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];

    let unitText = "All Units";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('income-by-unit-subtitle').textContent = `${monthNames[month-1]} ${year} | ${unitText}`;

    // Show loading state
    document.querySelector('.income-by-unit-content').classList.add('loading');

    // Fetch the data
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            // Process the data
            const units = data.units || [];
            const expenses = data.expenses || {};

            // Filter units based on selection
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            // Calculate income data for each unit
            const unitData = filteredUnits.map(unit => {
                const unitExpense = expenses[unit.id] || {};

                // Calculate sales income
                const salesIncome = parseFloat(unitExpense.sales || 0);

                // Calculate total expenses
                const totalExpenses =
                    parseFloat(unitExpense.rental || 0) +
                    parseFloat(unitExpense.electricity || 0) +
                    parseFloat(unitExpense.water || 0) +
                    parseFloat(unitExpense.sewage || 0) +
                    parseFloat(unitExpense.internet || 0) +
                    parseFloat(unitExpense.cleaner || 0) +
                    parseFloat(unitExpense.laundry || 0) +
                    parseFloat(unitExpense.supplies || 0) +
                    parseFloat(unitExpense.repair || 0) +
                    parseFloat(unitExpense.replace || 0) +
                    parseFloat(unitExpense.other || 0);

                // Calculate net profit
                const netProfit = salesIncome - totalExpenses;

                // Calculate profit margin
                const profitMargin = salesIncome > 0 ? (netProfit / salesIncome) * 100 : 0;

                return {
                    unitNumber: unit.unit_number,
                    salesIncome: salesIncome,
                    netProfit: netProfit,
                    profitMargin: profitMargin
                };
            });

            // Store data globally for sorting
            currentIncomeData = unitData;

            // Update the chart
            updateIncomeChart(unitData);

            // Update the table with current sort
            updateIncomeTable(unitData, currentIncomeSort);

            // Setup sorting (only needs to be called once, but safe to call multiple times)
            setupIncomeSorting();

            // Hide loading state
            document.querySelector('.income-by-unit-content').classList.remove('loading');
        })
        .catch(error => {
            console.error('Error fetching expense data:', error);
            document.querySelector('.income-by-unit-content').classList.remove('loading');
            document.querySelector('.income-by-unit-content').innerHTML = `
                <p class="error-message">Failed to load income data. Please try again.</p>
            `;
        });
}


// Function to update the income chart
function updateIncomeChart(unitData) {
    // Destroy existing chart if it exists
    if (window.incomeByUnitChart instanceof Chart) {
        window.incomeByUnitChart.destroy();
    }

    const ctx = document.getElementById('income-by-unit-chart').getContext('2d');

    // Prepare data for the chart
    const labels = unitData.map(item => item.unitNumber);
    const salesData = unitData.map(item => item.salesIncome);
    const profitData = unitData.map(item => item.netProfit);

    // Create the chart
    window.incomeByUnitChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Sales Income',
                    data: salesData,
                    backgroundColor: '#6BBBFA',
                    borderColor: '#6BBBFA',
                    borderWidth: 1
                },
                {
                    label: 'Net Profit',
                    data: profitData,
                    backgroundColor: '#66BB8A',
                    borderColor: '#66BB8A',
                    borderWidth: 1
                }
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: {
                        callback: function(value) {
                            return 'RM ' + value;
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': RM';
                            }
                            if (context.parsed.x !== null) {
                                label += context.parsed.x.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// Function to update the income table
function updateIncomeTable(unitData, sortConfig = { field: 'netProfit', direction: 'desc' }) {
    const tableBody = document.getElementById('income-table-body');
    tableBody.innerHTML = '';

    // Apply sorting
    unitData.sort((a, b) => {
        let aValue = a[sortConfig.field];
        let bValue = b[sortConfig.field];

        // For string values like unitNumber
        if (typeof aValue === 'string') {
            aValue = aValue.toLowerCase();
            bValue = bValue.toLowerCase();
        }

        if (sortConfig.direction === 'asc') {
            return aValue < bValue ? -1 : (aValue > bValue ? 1 : 0);
        } else {
            return aValue > bValue ? -1 : (aValue < bValue ? 1 : 0);
        }
    });

    let totalSalesIncome = 0;
    let totalNetProfit = 0;

    // Add rows for each unit
    unitData.forEach(item => {
        totalSalesIncome += item.salesIncome;
        totalNetProfit += item.netProfit;

        const row = document.createElement('tr');

        const unitCell = document.createElement('td');
        unitCell.textContent = item.unitNumber;
        row.appendChild(unitCell);

        const salesCell = document.createElement('td');
        salesCell.textContent = formatCurrency(item.salesIncome);
        row.appendChild(salesCell);

        const profitCell = document.createElement('td');
        profitCell.textContent = formatCurrency(item.netProfit);
        profitCell.style.color = item.netProfit >= 0 ? '#28a745' : '#dc3545';
        row.appendChild(profitCell);

        const marginCell = document.createElement('td');
        marginCell.textContent = item.profitMargin.toFixed(1) + '%';
        marginCell.style.color = item.profitMargin >= 0 ? '#28a745' : '#dc3545';
        row.appendChild(marginCell);

        tableBody.appendChild(row);
    });

    // Update totals
    document.getElementById('total-sales-income').textContent = formatCurrency(totalSalesIncome);

    const totalProfitElement = document.getElementById('total-net-profit');
    totalProfitElement.textContent = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(totalNetProfit);
    totalProfitElement.style.color = totalNetProfit >= 0 ? '#28a745' : '#dc3545';

    const totalMargin = totalSalesIncome > 0 ? (totalNetProfit / totalSalesIncome) * 100 : 0;
    const totalMarginElement = document.getElementById('total-profit-margin');
    totalMarginElement.textContent = totalMargin.toFixed(1) + '%';
    totalMarginElement.style.color = totalMargin >= 0 ? '#28a745' : '#dc3545';

    // Update header sorting indicators
    updateSortingIndicators(sortConfig);
}

// Global variable to store current sort state
let currentIncomeSort = { field: 'netProfit', direction: 'desc' };
let currentIncomeData = [];

// Function to handle header clicks for sorting
function setupIncomeSorting() {
    const headers = document.querySelectorAll('#income-table-container th');

    // Map headers to their respective data fields
    const headerFields = {
        0: 'unitNumber',
        1: 'salesIncome',
        2: 'netProfit',
        3: 'profitMargin'
    };

    // Add click handlers to headers
    headers.forEach((header, index) => {
        if (index < Object.keys(headerFields).length) { // Skip if not in our mapping
            header.style.cursor = 'pointer';

            // Add subtle indicator that it's clickable
            header.title = 'Click to sort';

            // Add a sort indicator span
            if (!header.querySelector('.sort-indicator')) {
                const indicator = document.createElement('span');
                indicator.className = 'sort-indicator';
                indicator.style.marginLeft = '5px';
                indicator.innerHTML = '';
                header.appendChild(indicator);
            }

            header.addEventListener('click', function() {
                const field = headerFields[index];

                // Toggle direction if same field, otherwise default to ascending
                if (currentIncomeSort.field === field) {
                    currentIncomeSort.direction = currentIncomeSort.direction === 'asc' ? 'desc' : 'asc';
                } else {
                    currentIncomeSort.field = field;
                    currentIncomeSort.direction = 'asc';
                }

                // Update table with new sort
                updateIncomeTable(currentIncomeData, currentIncomeSort);
            });
        }
    });
}

// Function to update sorting indicators
function updateSortingIndicators(sortConfig) {
    const headers = document.querySelectorAll('#income-table-container th');
    const headerFields = {
        0: 'unitNumber',
        1: 'salesIncome',
        2: 'netProfit',
        3: 'profitMargin'
    };

    // Clear all indicators
    headers.forEach(header => {
        const indicator = header.querySelector('.sort-indicator');
        if (indicator) {
            indicator.innerHTML = '';
        }
    });

    // Set the active indicator
    for (let i = 0; i < headers.length; i++) {
        if (headerFields[i] === sortConfig.field) {
            const indicator = headers[i].querySelector('.sort-indicator');
            if (indicator) {
                indicator.innerHTML = sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
            }
            break;
        }
    }
}

// Helper function to format currency values
function formatCurrency(value) {
    return new Intl.NumberFormat('en-MY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

// Update the existing code that handles tab switching in the DOMContentLoaded event
document.addEventListener('DOMContentLoaded', function() {
    // ... existing code ...

    // Initialize Income by Unit Analysis
    initializeIncomeByUnitAnalysis();

    // Modify the existing event listener for analysis options
    const analysisOptions = document.querySelectorAll('.analysis-option');
    if (analysisOptions.length > 0) {
        analysisOptions.forEach(option => {
            option.addEventListener('click', function() {
                // Remove active class from all options
                analysisOptions.forEach(opt => opt.classList.remove('active'));

                // Add active class to clicked option
                this.classList.add('active');

                // Get the analysis type
                const analysisType = this.getAttribute('data-analysis');

                // Hide all analysis content
                document.querySelector('.analysis-content').style.display = 'none';
                document.querySelector('.pl-statement-content').style.display = 'none';
                document.querySelector('.yoy-comparison-content').style.display = 'none';
                document.querySelector('.roi-analysis-content').style.display = 'none';
                document.querySelector('.income-by-unit-content').style.display = 'none';

                // Show the selected analysis content
                if (analysisType === 'expenses-breakdown') {
                    document.querySelector('.analysis-content').style.display = 'block';
                    updateAnalysis(); // Refresh the data
                } else if (analysisType === 'pl-statement') {
                    document.querySelector('.pl-statement-content').style.display = 'block';
                    updatePnLStatement(); // Refresh the data
                } else if (analysisType === 'yoy-comparison') {
                    document.querySelector('.yoy-comparison-content').style.display = 'block';
                    updateYoYComparison(); // Load the YoY comparison data
                } else if (analysisType === 'roi-analysis') {
                    document.querySelector('.roi-analysis-content').style.display = 'block';
                    updateROIAnalysis(); // Load the ROI analysis data
                } else if (analysisType === 'income-by-unit') {
                    document.querySelector('.income-by-unit-content').style.display = 'block';
                    updateIncomeByUnitAnalysis(); // Load the Income by Unit data
                }
            });
        });
    }

    // Also update these listeners to handle the new tab
    document.getElementById('analysis-month-year')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });

    document.getElementById('analysis-unit')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });
});

// Add a click event handler to the Unit column header
document.addEventListener('DOMContentLoaded', function() {
    const unitHeader = document.querySelector('#expenses-table th.unit-column');
    if (unitHeader) {
        unitHeader.style.cursor = 'pointer'; // Add pointer cursor to indicate it's clickable
        unitHeader.addEventListener('click', function() {
            sortExpensesTableByUnit();
        });
    }
});

// Function to sort the expenses table by unit
function sortExpensesTableByUnit() {
    // Get the table body and all rows
    const tableBody = document.getElementById('expenses-data');
    const rows = Array.from(tableBody.querySelectorAll('tr'));

    // Track the current sort direction (toggle between asc and desc)
    const unitHeader = document.querySelector('#expenses-table th.unit-column');
    const currentDirection = unitHeader.getAttribute('data-sort-direction') || 'asc';
    const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';

    // Update the header with the new sort direction
    unitHeader.setAttribute('data-sort-direction', newDirection);

    // Clear any existing sort indicators
    document.querySelectorAll('#expenses-table th').forEach(th => {
        th.classList.remove('sorted-asc', 'sorted-desc');
    });

    // Add visual indicator for sort direction
    unitHeader.classList.add('sorted-' + newDirection);

    // Sort the rows based on unit name
    rows.sort((a, b) => {
        const unitA = a.querySelector('.unit-column').textContent.trim().toLowerCase();
        const unitB = b.querySelector('.unit-column').textContent.trim().toLowerCase();

        if (newDirection === 'asc') {
            return unitA.localeCompare(unitB);
        } else {
            return unitB.localeCompare(unitA);
        }
    });

    // Re-append rows in the new order
    rows.forEach(row => {
        tableBody.appendChild(row);
    });
}


// Function to handle Enter key press and move to the cell below
document.addEventListener('DOMContentLoaded', function() {
    // Get the expenses table
    const expensesTable = document.getElementById('expenses-table');
    if (!expensesTable) return;

    // Add keydown event listener to the table
    expensesTable.addEventListener('keydown', function(event) {
        // Check if the event is Enter key
        if (event.key === 'Enter') {
            // Prevent default behavior (which might submit a form)
            event.preventDefault();

            // Get the current active element (should be an input)
            const currentInput = document.activeElement;

            // Make sure we're in an input element inside a table cell
            if (currentInput.tagName === 'INPUT' && currentInput.closest('td.editable')) {
                // Get current row and cell
                const currentRow = currentInput.closest('tr');
                const currentCell = currentInput.closest('td');

                // Get all rows in the table body
                const allRows = Array.from(document.querySelectorAll('#expenses-data tr'));

                // Get the index of the current row
                const currentRowIndex = allRows.indexOf(currentRow);

                // Get all editable cells in the current row
                const allCellsInRow = Array.from(currentRow.querySelectorAll('td.editable'));

                // Get the index of the current cell
                const currentCellIndex = allCellsInRow.indexOf(currentCell);

                // Check if there's a next row
                if (currentRowIndex < allRows.length - 1) {
                    // Get the next row
                    const nextRow = allRows[currentRowIndex + 1];

                    // Get the same column in the next row
                    const nextCell = nextRow.querySelectorAll('td.editable')[currentCellIndex];

                    // If the cell exists, focus on its input
                    if (nextCell) {
                        const nextInput = nextCell.querySelector('input');
                        if (nextInput) {
                            nextInput.focus();

                            // Optionally select all text in the input for easy replacement
                            nextInput.select();
                        }
                    }
                }
            }
        }
    });
});


/**
 * Initialize cell remarks functionality
 */
// Function to initialize the right-click functionality
function initCellRemarks() {
    // Add right-click event listener to the table
    document.getElementById('expenses-data').addEventListener('contextmenu', function(e) {
        // Prevent the default context menu
        e.preventDefault();

        // Check if we clicked on an input inside an editable cell
        const input = e.target.closest('input');
        if (!input) return;

        // Get the cell and its position
        const cell = input.closest('td');
        if (!cell || !cell.classList.contains('editable')) return;

        // Show the remark popup
        showRemarkPopup(input, e.clientX, e.clientY);
    });

    // Add keyboard shortcut (Ctrl+R) for adding remarks
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'r') {
            const activeElement = document.activeElement;
            if (activeElement.tagName === 'INPUT' && activeElement.closest('td.editable')) {
                e.preventDefault();
                const rect = activeElement.getBoundingClientRect();
                showRemarkPopup(activeElement, rect.left, rect.bottom);
            }
        }
    });

    // Close popup when clicking outside
    document.addEventListener('click', function(e) {
        const popup = document.getElementById('remark-popup');
        if (popup && !popup.contains(e.target) && e.target.id !== 'remark-popup') {
            popup.remove();
        }
    });
}


/**
 * Show the remark popup for a cell
 * @param {Element} input - The input element in the cell
 * @param {number} x - The x position for the popup
 * @param {number} y - The y position for the popup
 */
// Complete solution that preserves both right-click functionality and showing all remarks

// First, ensure the showRemarkPopup function is properly defined
function showRemarkPopup(input, x, y) {
    // Remove any existing popup
    const existingPopup = document.getElementById('remark-popup');
    if (existingPopup) {
        existingPopup.remove();
    }

    // Get unit ID and column from the input's data attributes
    const unitId = input.dataset.unitId;
    const column = input.dataset.column;

    // Get existing remark if any
    let existingRemark = '';
    if (window.expensesManager.currentRemarks &&
        window.expensesManager.currentRemarks[unitId] &&
        window.expensesManager.currentRemarks[unitId][column]) {
        existingRemark = window.expensesManager.currentRemarks[unitId][column];
    }

    // Create the popup
    const popup = document.createElement('div');
    popup.id = 'remark-popup';
    popup.style.position = 'fixed';
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
    popup.style.zIndex = '1000';
    popup.style.backgroundColor = 'white';
    popup.style.border = '1px solid #ddd';
    popup.style.borderRadius = '4px';
    popup.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
    popup.style.padding = '10px';
    popup.style.width = '300px';

    // Create the content
    popup.innerHTML = `
        <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 16px;">Add Remark</h3>
        <textarea id="remark-text" style="width: 100%; height: 100px; margin-bottom: 10px; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">${existingRemark}</textarea>
        <div style="display: flex; justify-content: space-between;">
            <button id="save-remark" style="padding: 8px 15px; background-color: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">Save</button>
            <button id="clear-remark" style="padding: 8px 15px; background-color: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer;">Clear</button>
            <button id="cancel-remark" style="padding: 8px 15px; background-color: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">Cancel</button>
        </div>
    `;

    // Append to body
    document.body.appendChild(popup);

    // Position the popup to ensure it's visible
    const popupRect = popup.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    if (popupRect.right > viewportWidth) {
        popup.style.left = (viewportWidth - popupRect.width - 10) + 'px';
    }

    if (popupRect.bottom > viewportHeight) {
        popup.style.top = (viewportHeight - popupRect.height - 10) + 'px';
    }

    // Focus the textarea
    document.getElementById('remark-text').focus();

    // Add event listeners
    document.getElementById('save-remark').addEventListener('click', function() {
        const remarkText = document.getElementById('remark-text').value.trim();
        saveRemark(unitId, column, remarkText, input);
        popup.remove();
    });

    document.getElementById('clear-remark').addEventListener('click', function() {
        saveRemark(unitId, column, '', input);
        popup.remove();
    });

    document.getElementById('cancel-remark').addEventListener('click', function() {
        popup.remove();
    });
}

// Make sure the saveRemark function is defined
function saveRemark(unitId, column, remark, input) {
    // Initialize remarks object if needed
    if (!window.expensesManager.currentRemarks) {
        window.expensesManager.currentRemarks = {};
    }

    if (!window.expensesManager.currentRemarks[unitId]) {
        window.expensesManager.currentRemarks[unitId] = {};
    }

    // Save or clear the remark
    if (remark) {
        window.expensesManager.currentRemarks[unitId][column] = remark;

        // Add visual indicator to the cell
        const cell = input.closest('td');
        addRemarkIndicator(cell);
    } else {
        // Remove the remark
        delete window.expensesManager.currentRemarks[unitId][column];

        // Remove visual indicator from the cell
        const cell = input.closest('td');
        removeRemarkIndicator(cell);
    }
}

// Add visual indicator
function addRemarkIndicator(cell) {
    // Check if indicator already exists
    if (cell.querySelector('.remark-indicator')) return;

    // Add the indicator
    const indicator = document.createElement('div');
    indicator.className = 'remark-indicator';
    indicator.style.position = 'absolute';
    indicator.style.top = '0';
    indicator.style.right = '0';
    indicator.style.width = '0';
    indicator.style.height = '0';
    indicator.style.borderStyle = 'solid';
    indicator.style.borderWidth = '0 10px 10px 0';
    indicator.style.borderColor = 'transparent #ee4d2d transparent transparent';

    // Ensure the cell has position relative
    if (getComputedStyle(cell).position !== 'relative') {
        cell.style.position = 'relative';
    }

    cell.appendChild(indicator);
}

// Remove visual indicator
function removeRemarkIndicator(cell) {
    const indicator = cell.querySelector('.remark-indicator');
    if (indicator) {
        indicator.remove();
    }
}


/**
 * Remove a visual indicator from a cell
 * @param {Element} cell - The cell element
 */
function removeRemarkIndicator(cell) {
    const indicator = cell.querySelector('.remark-indicator');
    if (indicator) {
        indicator.remove();
    }
}

/**
 * Update the saveExpensesData function to include remarks
 */
ExpensesManager.prototype._originalSaveExpensesData = ExpensesManager.prototype.saveExpensesData;
ExpensesManager.prototype.saveExpensesData = function() {
    // Call the original method
    this._originalSaveExpensesData();

    // Also save the remarks
    this.saveRemarks();
};

/**
 * Save remarks to the server
 */
ExpensesManager.prototype.saveRemarks = function() {
    if (!this.currentRemarks) return;

    // Get selected month-year
    const [year, month] = this.monthFilter.value.split('-');

    // Prepare data for saving
    const data = {
        year: year,
        month: month,
        remarks: this.currentRemarks
    };

    // Make API request to save data
    fetch('/api/expenses/remarks', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to save remarks');
        }
        return response.json();
    })
    .then(result => {
        console.log('Remarks saved successfully');
    })
    .catch(error => {
        console.error('Error saving remarks:', error);
        // Show error in a non-intrusive way
        const errorMsg = document.createElement('div');
        errorMsg.textContent = 'Failed to save remarks. Please try again.';
        errorMsg.style.color = '#f44336';
        errorMsg.style.padding = '5px';
        errorMsg.style.marginTop = '5px';

        // Insert after save message
        const saveMessage = document.getElementById('save-message');
        saveMessage.parentNode.insertBefore(errorMsg, saveMessage.nextSibling);

        // Remove after 3 seconds
        setTimeout(() => {
            errorMsg.remove();
        }, 3000);
    });
};

/**
 * Load remarks from the server when loading expenses data
 */
ExpensesManager.prototype._originalLoadExpensesData = ExpensesManager.prototype.loadExpensesData;
ExpensesManager.prototype.loadExpensesData = function() {
    // Call the original method first
    this._originalLoadExpensesData();

    // Then load remarks
    this.loadRemarks();
};

/**
 * Load remarks from the server
 */
ExpensesManager.prototype.loadRemarks = function() {
    // Get selected month-year
    const [year, month] = this.monthFilter.value.split('-');

    // Make API request to get remarks
    fetch(`/api/expenses/remarks?year=${year}&month=${month}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to load remarks');
            }
            return response.json();
        })
        .then(data => {
            // Store the remarks
            this.currentRemarks = data.remarks || {};

            // Apply remark indicators to cells
            this.applyRemarkIndicators();
        })
        .catch(error => {
            console.error('Error loading remarks:', error);
            // Reset remarks to empty object
            this.currentRemarks = {};
        });
};

/**
 * Apply remark indicators to cells based on loaded remarks
 */
ExpensesManager.prototype.applyRemarkIndicators = function() {
    if (!this.currentRemarks) return;

    // Loop through all inputs in the table
    const inputs = document.querySelectorAll('#expenses-data td.editable input');
    inputs.forEach(input => {
        const unitId = input.dataset.unitId;
        const column = input.dataset.column;

        // Check if there's a remark for this cell
        if (this.currentRemarks[unitId] && this.currentRemarks[unitId][column]) {
            // Add indicator to the cell
            const cell = input.closest('td');
            addRemarkIndicator(cell);
        }
    });
};

/**
 * Show remark when hovering over a cell with a remark
 */
/**
 * Show remark when hovering over a cell with a remark
 */
/**
 * Show remark when hovering over a cell with a remark
 */
function initRemarkTooltips() {
    // Create a tooltip element
    const tooltip = document.createElement('div');
    tooltip.id = 'remark-tooltip';
    tooltip.style.position = 'absolute';
    tooltip.style.display = 'none';
    tooltip.style.backgroundColor = '#fffde7';
    tooltip.style.border = '1px solid #ffd600';
    tooltip.style.borderRadius = '4px';
    tooltip.style.padding = '8px 12px';
    tooltip.style.maxWidth = '300px';
    tooltip.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
    tooltip.style.zIndex = '1001';
    tooltip.style.fontSize = '14px';
    tooltip.style.lineHeight = '1.4';

    document.body.appendChild(tooltip);

    // Track current active cell for tooltip
    let activeCell = null;

    // Delegation for hover events
    document.getElementById('expenses-data').addEventListener('mouseover', function(e) {
        const cell = e.target.closest('td.editable');
        if (!cell) return;

        // Check if the cell has a remark indicator
        const indicator = cell.querySelector('.remark-indicator');
        if (!indicator) return;

        // Update active cell
        activeCell = cell;

        // Find the input to get unit and column
        const input = cell.querySelector('input');
        if (!input) return;

        const unitId = input.dataset.unitId;
        const column = input.dataset.column;

        // Get the remark text
        if (window.expensesManager.currentRemarks &&
            window.expensesManager.currentRemarks[unitId] &&
            window.expensesManager.currentRemarks[unitId][column]) {

            const remarkText = window.expensesManager.currentRemarks[unitId][column];

            // Show the tooltip
            tooltip.textContent = remarkText;
            tooltip.style.display = 'block';

            // Position the tooltip
            const cellRect = cell.getBoundingClientRect();
            tooltip.style.left = cellRect.left + 'px';
            tooltip.style.top = (cellRect.bottom + window.scrollY + 5) + 'px';
        }
    });

    // Fix: Improve mouseout handling
    document.getElementById('expenses-data').addEventListener('mouseout', function(e) {
        // If we're moving from a cell to something outside the cell, hide the tooltip
        const cell = e.target.closest('td.editable');
        if (!cell) return;

        // Get the element we're moving to
        const relatedTarget = e.relatedTarget;

        // If we're moving out of the cell (not to a child of the cell), hide the tooltip
        if (!cell.contains(relatedTarget)) {
            tooltip.style.display = 'none';
            activeCell = null;
        }
    });

    // Also hide tooltip when mouse leaves the table
    document.getElementById('expenses-table').addEventListener('mouseleave', function() {
        tooltip.style.display = 'none';
        activeCell = null;
    });

    // Add global document listeners to ensure tooltip disappears
    document.addEventListener('click', function(e) {
        // Don't hide if clicking within the active cell
        if (activeCell && activeCell.contains(e.target)) return;

        tooltip.style.display = 'none';
        activeCell = null;
    });

    document.addEventListener('scroll', function() {
        tooltip.style.display = 'none';
        activeCell = null;
    });

    // Hide tooltip when tab changes
    const tabs = document.querySelectorAll('.expenses-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            tooltip.style.display = 'none';
            activeCell = null;
        });
    });

    // Hide tooltip when changing pages
    window.addEventListener('beforeunload', function() {
        tooltip.style.display = 'none';
    });
}


// Add this code to your expenses.js file, just before the closing bracket of the initCellRemarks function

// Add a "Show Remarks" button
function addShowRemarksButton() {
    // Create the button
    const showRemarksBtn = document.createElement('button');
    showRemarksBtn.id = 'show-remarks-btn';
    showRemarksBtn.className = 'action-btn';
    showRemarksBtn.innerHTML = '<i class="fas fa-comment"></i> Show All Remarks';
    showRemarksBtn.style.backgroundColor = '#4169E1';
    showRemarksBtn.style.color = 'white';
    showRemarksBtn.style.marginLeft = '10px';

    // Find the existing buttons container
    const actionsContainer = document.querySelector('.expenses-actions');
    if (actionsContainer) {
        // Add button after the reload button
        const reloadBtn = document.getElementById('reload-btn');
        if (reloadBtn) {
            reloadBtn.parentNode.insertBefore(showRemarksBtn, reloadBtn.nextSibling);
        } else {
            actionsContainer.appendChild(showRemarksBtn);
        }
    }

    // Add click event listener
    showRemarksBtn.addEventListener('click', showAllRemarks);
}

// Function to show all remarks in a modal
function showAllRemarks() {
    // Check if we have any remarks
    if (!window.expensesManager.currentRemarks ||
        Object.keys(window.expensesManager.currentRemarks).length === 0) {
        alert('No remarks found for the current month.');
        return;
    }

    // Create a new modal overlay
    const overlay = document.createElement('div');
    overlay.id = 'remarks-modal-overlay';
    overlay.className = 'modal-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    overlay.style.zIndex = '2000';
    overlay.style.display = 'flex';
    overlay.style.justifyContent = 'center';
    overlay.style.alignItems = 'center';

    // Create modal content
    const modal = document.createElement('div');
    modal.className = 'remarks-modal';
    modal.style.backgroundColor = 'white';
    modal.style.borderRadius = '8px';
    modal.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.2)';
    modal.style.padding = '20px';
    modal.style.width = '80%';
    modal.style.maxWidth = '900px';
    modal.style.maxHeight = '80vh';
    modal.style.overflowY = 'auto';

    // Add modal header
    const header = document.createElement('div');
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.style.marginBottom = '20px';
    header.style.paddingBottom = '10px';
    header.style.borderBottom = '1px solid #eee';

    // Get current month-year for title
    const [year, month] = window.expensesManager.monthFilter.value.split('-');
    const date = new Date(year, month - 1);
    const monthName = date.toLocaleString('default', { month: 'long' });

    // Add title
    const title = document.createElement('h2');
    title.textContent = `Remarks for ${monthName} ${year}`;
    title.style.margin = '0';

    // Add close button
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.background = 'none';
    closeBtn.style.border = 'none';
    closeBtn.style.fontSize = '24px';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.padding = '0 5px';
    closeBtn.title = 'Close';

    // Append header elements
    header.appendChild(title);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // Create remarks table
    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';

    // Add table header
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th style="text-align: left; padding: 10px; border-bottom: 2px solid #ddd; background-color: #f5f7f9;">Unit</th>
            <th style="text-align: left; padding: 10px; border-bottom: 2px solid #ddd; background-color: #f5f7f9;">Column</th>
            <th style="text-align: left; padding: 10px; border-bottom: 2px solid #ddd; background-color: #f5f7f9;">Value</th>
            <th style="text-align: left; padding: 10px; border-bottom: 2px solid #ddd; background-color: #f5f7f9;">Remark</th>
            <th style="text-align: center; padding: 10px; border-bottom: 2px solid #ddd; background-color: #f5f7f9;">Actions</th>
        </tr>
    `;
    table.appendChild(thead);

    // Add table body
    const tbody = document.createElement('tbody');

    // Get all rows from the expenses table
    const expensesTable = document.getElementById('expenses-table');
    const rows = expensesTable.querySelectorAll('tbody tr');

    // Map to store unit numbers by ID
    const unitMap = {};

    // Populate unit map
    rows.forEach(row => {
        const unitCell = row.querySelector('.unit-column');
        if (unitCell) {
            const unitName = unitCell.textContent.trim();
            const inputs = row.querySelectorAll('input');
            if (inputs.length > 0) {
                const unitId = inputs[0].dataset.unitId;
                if (unitId) {
                    unitMap[unitId] = unitName;
                }
            }
        }
    });

    // Column names mapping
    const columnNames = {
        'sales': 'Sales',
        'rental': 'Rental',
        'electricity': 'Electricity',
        'water': 'Water',
        'sewage': 'Sewage',
        'internet': 'Internet',
        'cleaner': 'Cleaner',
        'laundry': 'Laundry',
        'supplies': 'Supplies',
        'repair': 'Repair',
        'replace': 'Replace',
        'other': 'Other'
    };

    // Populate table with remarks
    let remarkCount = 0;

    for (const unitId in window.expensesManager.currentRemarks) {
        const unitName = unitMap[unitId] || `Unit ID: ${unitId}`;

        for (const column in window.expensesManager.currentRemarks[unitId]) {
            const remark = window.expensesManager.currentRemarks[unitId][column];
            if (!remark) continue;

            remarkCount++;

            // Get the current value from the input
            let cellValue = '';
            const input = document.querySelector(`input[data-unit-id="${unitId}"][data-column="${column}"]`);
            if (input) {
                cellValue = input.value;
            }

            // Create table row
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="padding: 10px; border-bottom: 1px solid #eee;">${unitName}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">${columnNames[column] || column}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">${cellValue}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; white-space: pre-wrap;">${remark}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                    <button class="edit-remark-btn" data-unit-id="${unitId}" data-column="${column}" style="background-color: #4169E1; color: white; border: none; border-radius: 4px; padding: 5px 10px; margin-right: 5px; cursor: pointer;">Edit</button>
                    <button class="delete-remark-btn" data-unit-id="${unitId}" data-column="${column}" style="background-color: #dc3545; color: white; border: none; border-radius: 4px; padding: 5px 10px; cursor: pointer;">Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        }
    }

    // Add table to modal
    table.appendChild(tbody);
    modal.appendChild(table);

    // Add "No remarks" message if needed
    if (remarkCount === 0) {
        const noRemarks = document.createElement('p');
        noRemarks.textContent = 'No remarks found for the current month.';
        noRemarks.style.textAlign = 'center';
        noRemarks.style.color = '#666';
        noRemarks.style.padding = '20px';
        modal.appendChild(noRemarks);
    }

    // Add modal to overlay
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Add close button click event
    closeBtn.addEventListener('click', function() {
        overlay.remove();
    });

    // Click outside to close
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
        }
    });

    // FIXED: Event delegation for edit and delete buttons
    modal.addEventListener('click', function(e) {
        // Find the closest button if a child element was clicked
        const button = e.target.closest('.edit-remark-btn, .delete-remark-btn');
        if (!button) return; // Not a button click

        const unitId = button.getAttribute('data-unit-id');
        const column = button.getAttribute('data-column');

        // Handle Edit button click
        if (button.classList.contains('edit-remark-btn')) {
            // Find the input element
            const input = document.querySelector(`input[data-unit-id="${unitId}"][data-column="${column}"]`);
            if (input) {
                // Close the modal
                overlay.remove();

                // Get the cell and position for the popup
                const cell = input.closest('td');
                const rect = cell.getBoundingClientRect();

                // Show the remark popup
                showRemarkPopup(input, rect.left, rect.bottom);

                // Scroll to the cell
                cell.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });

                // Highlight the cell temporarily
                const originalBackground = cell.style.backgroundColor;
                cell.style.backgroundColor = '#fffde7';

                setTimeout(() => {
                    cell.style.backgroundColor = originalBackground;
                }, 2000);
            }
        }
        // Handle Delete button click
        else if (button.classList.contains('delete-remark-btn')) {
            if (confirm('Are you sure you want to delete this remark?')) {
                // Find the input element
                const input = document.querySelector(`input[data-unit-id="${unitId}"][data-column="${column}"]`);
                if (input) {
                    // Remove the remark
                    saveRemark(unitId, column, '', input);

                    // Remove the table row
                    const row = button.closest('tr');
                    row.remove();

                    // Update remark count
                    remarkCount--;

                    // Show "No remarks" message if needed
                    if (remarkCount === 0) {
                        const noRemarks = document.createElement('p');
                        noRemarks.textContent = 'No remarks found for the current month.';
                        noRemarks.style.textAlign = 'center';
                        noRemarks.style.color = '#666';
                        noRemarks.style.padding = '20px';
                        modal.appendChild(noRemarks);
                    }
                }
            }
        }
    });
}

// Implement the showAllRemarks button functionality
// Replace the DOMContentLoaded event listener at the bottom of the previous code with this version
// that checks for an existing button before creating a new one:




// Add this code to your expenses.js file
// This implements a toggle button for highlighting cells with remarks

// Global variable to track highlight state
let remarksHighlightActive = false;

// Function to create the toggle button
function createRemarksToggleButton() {
    // Create the toggle button
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'toggle-remarks-btn';
    toggleBtn.className = 'action-btn';
    toggleBtn.innerHTML = 'Highlight Remarks';
    toggleBtn.style.backgroundColor = '#6c757d';
    toggleBtn.style.color = 'white';
    toggleBtn.style.marginLeft = '10px';

    // Add click event listener
    toggleBtn.addEventListener('click', toggleRemarksHighlight);

    return toggleBtn;
}

// Function to toggle remarks highlight
function toggleRemarksHighlight() {
    remarksHighlightActive = !remarksHighlightActive;
    const toggleBtn = document.getElementById('toggle-remarks-btn');

    // Update button style based on state
    if (remarksHighlightActive) {
        toggleBtn.style.backgroundColor = '#007bff';
        toggleBtn.innerHTML = 'Hide Remarks';
        highlightRemarkCells();
    } else {
        toggleBtn.style.backgroundColor = '#6c757d';
        toggleBtn.innerHTML = 'Highlight Remarks';
        removeRemarkHighlights();
    }
}

// Function to highlight all cells with remarks
function highlightRemarkCells() {
    if (!window.expensesManager.currentRemarks) return;

    // Get all cells with remarks
    const cells = document.querySelectorAll('.editable input');
    cells.forEach(input => {
        const unitId = input.dataset.unitId;
        const column = input.dataset.column;

        if (window.expensesManager.currentRemarks[unitId] &&
            window.expensesManager.currentRemarks[unitId][column]) {

            const cell = input.closest('td');
            const remark = window.expensesManager.currentRemarks[unitId][column];

            // Highlight the cell
            cell.style.backgroundColor = '#e6f2ff';
            cell.style.position = 'relative';

            // Add tooltip for the remark if it doesn't exist
            if (!cell.querySelector('.remark-tooltip')) {
                const tooltip = document.createElement('div');
                tooltip.className = 'remark-tooltip';
                tooltip.textContent = remark;
                tooltip.style.position = 'absolute';
                tooltip.style.bottom = '110%';
                tooltip.style.left = '0';
                tooltip.style.backgroundColor = '#333';
                tooltip.style.color = 'white';
                tooltip.style.padding = '5px 10px';
                tooltip.style.borderRadius = '4px';
                tooltip.style.fontSize = '12px';
                tooltip.style.zIndex = '100';
                tooltip.style.whiteSpace = 'pre-wrap';
                tooltip.style.maxWidth = '200px';
                tooltip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
                tooltip.style.opacity = '0';
                tooltip.style.transition = 'opacity 0.3s';

                // Add arrow
                const arrow = document.createElement('div');
                arrow.style.position = 'absolute';
                arrow.style.bottom = '-5px';
                arrow.style.left = '10px';
                arrow.style.width = '0';
                arrow.style.height = '0';
                arrow.style.borderLeft = '5px solid transparent';
                arrow.style.borderRight = '5px solid transparent';
                arrow.style.borderTop = '5px solid #333';
                tooltip.appendChild(arrow);

                cell.appendChild(tooltip);

                // Show/hide tooltip on hover
                cell.addEventListener('mouseenter', () => {
                    if (remarksHighlightActive) {
                        tooltip.style.opacity = '1';
                    }
                });

                cell.addEventListener('mouseleave', () => {
                    tooltip.style.opacity = '0';
                });
            } else {
                // Update existing tooltip content
                const tooltip = cell.querySelector('.remark-tooltip');
                tooltip.textContent = remark;
            }
        }
    });
}

// Function to remove all highlights
function removeRemarkHighlights() {
    const highlightedCells = document.querySelectorAll('.editable td');
    highlightedCells.forEach(cell => {
        // Remove background color
        if (cell.style.backgroundColor === 'rgb(230, 242, 255)') { // #e6f2ff in rgb
            cell.style.backgroundColor = '';
        }

        // Hide tooltips
        const tooltip = cell.querySelector('.remark-tooltip');
        if (tooltip) {
            tooltip.remove();
        }
    });
}

// Update the DOMContentLoaded event to include the toggle button
document.addEventListener('DOMContentLoaded', function() {
    // First, check if there is already a button in the DOM
    let showAllRemarksBtn = document.getElementById('show-all-remarks-btn');

    // If there are multiple buttons, remove all but the first one
    const existingButtons = document.querySelectorAll('#show-all-remarks-btn');
    if (existingButtons.length > 1) {
        for (let i = 1; i < existingButtons.length; i++) {
            existingButtons[i].remove();
        }
        showAllRemarksBtn = existingButtons[0]; // Keep a reference to the first one
    }

    // If there's no button at all, create one
    if (!showAllRemarksBtn) {
        const reloadBtn = document.getElementById('reload-btn');
        if (reloadBtn) {
            showAllRemarksBtn = document.createElement('button');
            showAllRemarksBtn.id = 'show-all-remarks-btn';
            showAllRemarksBtn.className = 'action-btn';
            showAllRemarksBtn.innerHTML = 'Show All Remarks';
            showAllRemarksBtn.style.backgroundColor = '#6c757d';
            showAllRemarksBtn.style.color = 'white';
            showAllRemarksBtn.style.marginLeft = '10px';

            // Add button after the reload button
            reloadBtn.parentNode.insertBefore(showAllRemarksBtn, reloadBtn.nextSibling);
        }
    }

    // Ensure the button has the correct event listener
    if (showAllRemarksBtn) {
        // Remove any existing event listeners by cloning the node
        const newBtn = showAllRemarksBtn.cloneNode(true);
        if (showAllRemarksBtn.parentNode) {
            showAllRemarksBtn.parentNode.replaceChild(newBtn, showAllRemarksBtn);
        }

        // Add the event listener to the new button
        newBtn.addEventListener('click', showAllRemarks);

        // Create and add the toggle button after the show all remarks button
        const toggleBtn = createRemarksToggleButton();
        newBtn.parentNode.insertBefore(toggleBtn, newBtn.nextSibling);
    }

    // Initialize the right-click remarks functionality
    initCellRemarks();

    // Add helper text to inform users about the remark feature
    const helpText = document.createElement('div');
    helpText.innerHTML = '<p style="margin: 0 0 10px 0; font-size: 0.9rem; color: #666;">Right-click on a cell or press Ctrl+R to add remarks.</p>';

    // Insert the helper text after the filters and before the table
    const tableContainer = document.querySelector('.table-container');
    if (tableContainer && tableContainer.parentNode) {
        tableContainer.parentNode.insertBefore(helpText, tableContainer);
    }

    // Add event listener for month/building filter changes to reapply highlights if active
    document.getElementById('month-filter')?.addEventListener('change', function() {
        // Wait for the data to load
        setTimeout(() => {
            if (remarksHighlightActive) {
                highlightRemarkCells();
            }
        }, 1000);
    });

    document.getElementById('building-filter')?.addEventListener('change', function() {
        // Wait for the data to load
        setTimeout(() => {
            if (remarksHighlightActive) {
                highlightRemarkCells();
            }
        }, 1000);
    });
});

// Update the loadExpensesData method to reapply highlights if active
const originalLoadExpensesDataMethod = window.ExpensesManager.prototype.loadExpensesData;
window.ExpensesManager.prototype.loadExpensesData = function() {
    // Call the original method
    originalLoadExpensesDataMethod.call(this);

    // Reapply highlights if the toggle is active
    setTimeout(() => {
        if (remarksHighlightActive) {
            highlightRemarkCells();
        }
    }, 1000);
};

// Update the applyRemarkIndicators method to also highlight cells if toggle is active
const originalApplyRemarkIndicatorsMethod = window.ExpensesManager.prototype.applyRemarkIndicators;
window.ExpensesManager.prototype.applyRemarkIndicators = function() {
    // Call the original method
    originalApplyRemarkIndicatorsMethod.call(this);

    // Reapply highlights if the toggle is active
    if (remarksHighlightActive) {
        highlightRemarkCells();
    }
};