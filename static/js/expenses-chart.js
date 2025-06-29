// This script adds an interactive chart to the Charts tab in expenses.html

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the expenses chart functionality when the DOM is loaded
    initializeExpensesChart();
});


// Add this function to populate the buildings dropdown
function populateBuildingDropdown() {
    const buildingSelect = document.getElementById('chart-building-select');

    // Get buildings from the main page filter
    const mainBuildingFilter = document.getElementById('building-filter');

    // Clear existing options except "All Buildings"
    while (buildingSelect.options.length > 1) {
        buildingSelect.remove(1);
    }

    // Copy options from the main building filter
    if (mainBuildingFilter) {
        Array.from(mainBuildingFilter.options).forEach(option => {
            if (option.value !== 'all') {
                const newOption = document.createElement('option');
                newOption.value = option.value;
                newOption.textContent = option.textContent;
                buildingSelect.appendChild(newOption);
            }
        });
    }
}


/**
 * Initialize the expenses chart tab with controls and chart
 */
function initializeExpensesChart() {
    // Check if we're on the expenses page with the charts tab
    const chartsTab = document.getElementById('charts-tab');
    if (!chartsTab) return;

    // Replace the "Coming Soon" placeholder with our chart UI
    chartsTab.innerHTML = createChartUI();

    // Initialize the chart after creating the UI
    const ctx = document.getElementById('expenses-chart').getContext('2d');
    window.expensesChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            datasets: []
        },
        options: createChartOptions()
    });

    // Set up event listeners for the controls
    setupEventListeners();

    // Initialize data fields checkboxes
    initializeDataFieldsSelection();

    // Populate year dropdown with available years
    populateYearDropdown();

    // Populate unit dropdown with available units
    populateUnitDropdown();

    // Add this line to populate buildings
    populateBuildingDropdown();

    // Generate initial chart with default values
    updateChart();
}

/**
 * Create the chart UI with controls and the canvas
 */
function createChartUI() {
    return `
        <div class="chart-container" style="padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; margin-bottom: 20px;">Monthly Expenses Chart</h3>

            <div class="chart-controls" style="display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 8px;">
                <div style="flex: 1; min-width: 200px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Select Year:</label>
                    <select id="chart-year-select" class="report-select" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ddd;">
                        <!-- Years will be populated dynamically -->
                    </select>
                </div>

                <div style="flex: 1; min-width: 200px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Select Unit:</label>
                    <select id="chart-unit-select" class="report-select" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ddd;">
                        <option value="all">All Units</option>
                        <!-- Units will be populated dynamically -->
                    </select>
                </div>

                <div style="flex: 1; min-width: 200px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: bold;">Select Building:</label>
                    <select id="chart-building-select" class="report-select" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ddd;">
                        <option value="all">All Buildings</option>
                        <!-- Buildings will be populated dynamically -->
                    </select>
                </div>

                <!-- REMOVED: Update Chart button -->
            </div>

            <div class="data-field-selector" style="margin-bottom: 20px;">
                <label style="display: block; margin-bottom: 10px; font-weight: bold;">Select Data to Display:</label>
                <div id="data-fields-container" style="display: flex; flex-wrap: wrap; gap: 10px;">
                    <!-- Data field checkboxes will be added here -->
                </div>
            </div>

            <div style="position: relative; height: 400px;">
                <canvas id="expenses-chart"></canvas>
            </div>

            <div id="chart-loading" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(255,255,255,0.8); display: flex; justify-content: center; align-items: center; display: none;">
                <div style="text-align: center;">
                    <div class="spinner" style="width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; animation: spin 2s linear infinite; margin: 0 auto 10px;"></div>
                    <p>Loading chart data...</p>
                </div>
            </div>
        </div>
    `;
}

/**
 * Create the chart options configuration
 */
function createChartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            title: {
                display: true,
                text: 'Monthly Expenses Overview',
                font: {
                    size: 16,
                    weight: 'bold'
                }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                callbacks: {
                    label: function(context) {
                        let label = context.dataset.label || '';
                        if (label) {
                            label += ': RM';
                        }
                        if (context.parsed.y !== null) {
                            label += new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(context.parsed.y);
                        }
                        return label;
                    }
                }
            },
            legend: {
                position: 'top',
                labels: {
                    boxWidth: 12,
                    usePointStyle: true,
                    pointStyle: 'circle'
                }
            }
        },
        scales: {
            x: {
                title: {
                    display: true,
                    text: 'Month'
                }
            },
            y: {
                title: {
                    display: true,
                    text: 'Amount (RM)'
                },
                ticks: {
                    callback: function(value) {
                        return 'RM ' + value.toFixed(2);
                    }
                }
            }
        },
        interaction: {
            intersect: false,
            mode: 'index'
        }
    };
}

/**
 * Set up event listeners for chart controls
 */
function setupEventListeners() {

    // Year select change - automatically update the chart
    document.getElementById('chart-year-select').addEventListener('change', function() {
        updateChart();
    });

    // Unit select change - automatically update the chart
    document.getElementById('chart-unit-select').addEventListener('change', function() {
        updateChart();
    });

    // Building select change - automatically update the chart (ADD THIS)
    document.getElementById('chart-building-select').addEventListener('change', function() {
        updateChart();
    });
}

    // Building select change - automatically update the chart
    document.getElementById('chart-building-select')?.addEventListener('change', function() {
        updateChart();
    });

/**
 * Initialize the data fields selection checkboxes
 */
function initializeDataFieldsSelection() {
    const dataFields = [
        { id: 'net_earn', name: 'Net Earn', color: '#4CAF50', checked: true },
        { id: 'sales', name: 'Sales', color: '#2196F3', checked: true },
        { id: 'rental', name: 'Rental', color: '#FF9800', checked: false },
        { id: 'electricity', name: 'Electricity', color: '#F44336', checked: false },
        { id: 'water', name: 'Water', color: '#03A9F4', checked: false },
        { id: 'sewage', name: 'Sewage', color: '#9C27B0', checked: false },
        { id: 'internet', name: 'Internet', color: '#607D8B', checked: false },
        { id: 'cleaner', name: 'Cleaner', color: '#795548', checked: false },
        { id: 'laundry', name: 'Laundry', color: '#E91E63', checked: false },
        { id: 'supplies', name: 'Supplies', color: '#CDDC39', checked: false },
        { id: 'repair', name: 'Repair', color: '#FF5722', checked: false },
        { id: 'replace', name: 'Replace', color: '#673AB7', checked: false },
        { id: 'other', name: 'Other', color: '#009688', checked: false }
    ];

    const container = document.getElementById('data-fields-container');

    dataFields.forEach(field => {
        const checkboxWrapper = document.createElement('div');
        checkboxWrapper.style.display = 'flex';
        checkboxWrapper.style.alignItems = 'center';
        checkboxWrapper.style.marginRight = '15px';

        // Create checkbox
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `field-${field.id}`;
        checkbox.value = field.id;
        checkbox.checked = field.checked;
        checkbox.style.marginRight = '5px';

        // Create color sample
        const colorSample = document.createElement('span');
        colorSample.style.display = 'inline-block';
        colorSample.style.width = '12px';
        colorSample.style.height = '12px';
        colorSample.style.backgroundColor = field.color;
        colorSample.style.marginRight = '5px';
        colorSample.style.borderRadius = '2px';

        // Create label
        const label = document.createElement('label');
        label.htmlFor = `field-${field.id}`;
        label.textContent = field.name;
        label.style.marginBottom = '0';
        label.style.fontSize = '0.9rem';

        // Add elements to wrapper
        checkboxWrapper.appendChild(checkbox);
        checkboxWrapper.appendChild(colorSample);
        checkboxWrapper.appendChild(label);

        // Add wrapper to container
        container.appendChild(checkboxWrapper);

        // Add event listener for checkbox change
        checkbox.addEventListener('change', updateChart);
    });
}

/**
 * Populate the year dropdown with available years
 */
/**
 * Populate the year dropdown with available years
 */
function populateYearDropdown() {
    const yearSelect = document.getElementById('chart-year-select');
    const currentYear = new Date().getFullYear();

    // First, try to fetch years from API
    fetch('/api/expenses/years')
        .then(response => response.json())
        .then(data => {
            const years = data.years || [];

            // If no years returned, add current year and a few previous years
            if (years.length === 0) {
                for (let i = 0; i < 3; i++) {
                    const year = currentYear - i;
                    const option = document.createElement('option');
                    option.value = year;
                    option.textContent = year;
                    yearSelect.appendChild(option);
                }
            } else {
                // Sort years in descending order
                years.sort((a, b) => b - a);

                // Add years to dropdown
                years.forEach(year => {
                    const option = document.createElement('option');
                    option.value = year;
                    option.textContent = year;
                    yearSelect.appendChild(option);
                });
            }

            // SET DEFAULT TO CURRENT YEAR - ADD THIS SECTION
            // Check if current year exists in the dropdown
            const currentYearOption = Array.from(yearSelect.options).find(option =>
                parseInt(option.value) === currentYear
            );

            if (currentYearOption) {
                // If current year exists, select it
                yearSelect.value = currentYear;
            } else {
                // If current year doesn't exist, select the first (most recent) year
                if (yearSelect.options.length > 0) {
                    yearSelect.value = yearSelect.options[0].value;
                }
            }
        })
        .catch(error => {
            console.error('Error fetching years:', error);

            // Fallback to current year if API fails
            for (let i = 0; i < 3; i++) {
                const year = currentYear - i;
                const option = document.createElement('option');
                option.value = year;
                option.textContent = year;
                yearSelect.appendChild(option);
            }

            // SET DEFAULT TO CURRENT YEAR IN FALLBACK TOO
            yearSelect.value = currentYear;
        });
}
/**
 * Populate the unit dropdown with available units
 */
function populateUnitDropdown() {
    const unitSelect = document.getElementById('chart-unit-select');

    fetch('/api/get_units')
        .then(response => response.json())
        .then(units => {
            // Add units to dropdown
            units.forEach(unit => {
                const option = document.createElement('option');
                option.value = unit.id;
                option.textContent = unit.unit_number;
                unitSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error fetching units:', error);
        });
}

/**
 * Update the chart based on selected options
 */
function updateChart() {
    // Show loading overlay
    document.getElementById('chart-loading').style.display = 'flex';

    // Get selected year and unit
    let year = document.getElementById('chart-year-select').value;
    const unitId = document.getElementById('chart-unit-select').value;
    const building = document.getElementById('chart-building-select').value;

    // Add this check to ensure year is never empty
    if (!year) {
        // Default to current year if not set
        year = new Date().getFullYear();
        // Also update the dropdown to show the current year
        document.getElementById('chart-year-select').value = year;
    }

    // Get selected data fields
    const selectedFields = Array.from(document.querySelectorAll('#data-fields-container input[type="checkbox"]:checked'))
        .map(checkbox => checkbox.value);

    // If no fields selected, show message and return
    if (selectedFields.length === 0) {
        alert('Please select at least one data field to display.');
        document.getElementById('chart-loading').style.display = 'none';
        return;
    }

    // Update chart title
    if (window.expensesChart) {
        window.expensesChart.options.plugins.title.text = `Monthly Expenses Overview (${year})`;

        // Add unit information if a specific unit is selected
        if (unitId !== 'all') {
            const unitSelect = document.getElementById('chart-unit-select');
            const unitName = unitSelect.options[unitSelect.selectedIndex].text;
            window.expensesChart.options.plugins.title.text += ` - ${unitName}`;
        }
    }

    // Fetch data from API
    fetchExpensesData(year, unitId, building)
        .then(data => {
            updateChartWithData(data, selectedFields);
            document.getElementById('chart-loading').style.display = 'none';
        })
        .catch(error => {
            console.error('Error updating chart:', error);
            document.getElementById('chart-loading').style.display = 'none';
            alert('Error loading chart data. Please try again.');
        });
}

/**
 * Fetch expenses data from the API
 */
function fetchExpensesData(year, unitId, building) {
    // Ensure year is not empty before making the request
    if (!year) {
        year = new Date().getFullYear();
    }

    // Define the building parameter
    building = building || 'all';

    return fetch(`/api/expenses/yearly?year=${year}&building=${building}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch data');
            }
            return response.json();
        })
        .then(data => {
            // Process the API response for our chart
            return processExpensesData(data, unitId);
        })
        .catch(error => {
            console.error('Error fetching yearly expense data:', error);
            // Return empty data structure as fallback
            return {
                units: [],
                monthlyData: {},
                fields: [
                    'sales', 'rental', 'electricity', 'water', 'sewage',
                    'internet', 'cleaner', 'laundry', 'supplies',
                    'repair', 'replace', 'other'
                ]
            };
        });
}

/**
 * Process the raw expenses data for the chart
 */
function processExpensesData(apiData, unitId) {
    const processedData = {
        units: apiData.units || [],
        monthlyData: {},
        fields: [
            'sales', 'rental', 'electricity', 'water', 'sewage',
            'internet', 'cleaner', 'laundry', 'supplies',
            'repair', 'replace', 'other'
        ]
    };

    // Initialize monthly data structure
    for (let month = 1; month <= 12; month++) {
        processedData.monthlyData[month] = {};
        processedData.fields.forEach(field => {
            processedData.monthlyData[month][field] = 0;
        });
        // Add net_earn field separately
        processedData.monthlyData[month]['net_earn'] = 0;
    }

    // Filter for selected unit if not "all"
    let unitsToProcess = processedData.units;
    if (unitId !== 'all') {
        unitsToProcess = processedData.units.filter(unit => unit.id == unitId);
    }

    // Process each unit's expense data
    unitsToProcess.forEach(unit => {
        const unitId = unit.id;
        const unitExpenses = apiData.expenses[unitId] || {};

        // For each month
        for (let month = 1; month <= 12; month++) {
            const monthData = unitExpenses[month] || {};

            // Sum up each field across units
            processedData.fields.forEach(field => {
                const value = parseFloat(monthData[field] || 0);
                processedData.monthlyData[month][field] += value;
            });

            // Calculate net earn (sales minus all expenses)
            const sales = parseFloat(monthData.sales || 0);
            const expenses = processedData.fields
                .filter(field => field !== 'sales')
                .reduce((sum, field) => sum + parseFloat(monthData[field] || 0), 0);

            processedData.monthlyData[month]['net_earn'] += (sales - expenses);
        }
    });

    return processedData;
}

/**
 * Update the chart with the processed data
 */
function updateChartWithData(processedData, selectedFields) {
    if (!window.expensesChart) return;

    // Define colors for each field
    const fieldColors = {
        'net_earn': '#4CAF50',
        'sales': '#2196F3',
        'rental': '#FF9800',
        'electricity': '#F44336',
        'water': '#03A9F4',
        'sewage': '#9C27B0',
        'internet': '#607D8B',
        'cleaner': '#795548',
        'laundry': '#E91E63',
        'supplies': '#CDDC39',
        'repair': '#FF5722',
        'replace': '#673AB7',
        'other': '#009688'
    };

    // Define display names for each field
    const fieldNames = {
        'net_earn': 'Net Earn',
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

    // Create datasets for each selected field
    const datasets = selectedFields.map(field => {
        // Get monthly values for this field
        const monthlyValues = Array.from({ length: 12 }, (_, i) => {
            const month = i + 1;
            return processedData.monthlyData[month][field] || 0;
        });

        return {
            label: fieldNames[field],
            data: monthlyValues,
            backgroundColor: fieldColors[field],
            borderColor: fieldColors[field],
            borderWidth: 2,
            tension: 0.1,
            fill: false
        };
    });

    // Update chart datasets
    window.expensesChart.data.datasets = datasets;
    window.expensesChart.update();
}