document.addEventListener("DOMContentLoaded", function() {
    const testTypeField = document.getElementById("id_test_type");
    const subTestField = document.getElementById("id_sub_tests");

    const subTestName = document.getElementById("subTestName");
    const subTestDetailText = document.getElementById("subTestDetailText");
    const subTestInstructionText = document.getElementById("subTestInstructionText");

    // Fetch and update SubTests based on selected TestType
    testTypeField.addEventListener("change", function() {
        const testTypeId = this.value;
        subTestField.innerHTML = ""; // Clear existing options

        if (!testTypeId) {
            let option = document.createElement("option");
            option.textContent = "Select a Test Type first";
            subTestField.appendChild(option);
            return;
        }

        fetch(`/dashboard/get-subtests/?test_type=${testTypeId}`)
            .then(response => response.json())
            .then(data => {
                if (data.sub_tests.length === 0) {
                    let option = document.createElement("option");
                    option.textContent = "No sub-tests available";
                    subTestField.appendChild(option);
                } else {
                    data.sub_tests.forEach(subTest => {
                        let option = document.createElement("option");
                        option.value = subTest.id;
                        option.textContent = subTest.name;
                        subTestField.appendChild(option);
                    });
                }
            })
            .catch(error => console.error("Error fetching sub-tests:", error));
    });

    // Fetch and display SubTest details when selected
    subTestField.addEventListener("change", function() {
        const subTestId = this.value;

        if (subTestId) {
            fetch(`?sub_test_id=${subTestId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        subTestName.textContent = "Error loading test details";
                        subTestDetailText.textContent = "-";
                        subTestInstructionText.textContent = "-";
                    } else {
                        subTestName.textContent = data.name;
                        subTestDetailText.textContent = data.details;
                        subTestInstructionText.textContent = data.instructions;
                    }
                })
                .catch(error => console.error("Error fetching SubTest details:", error));
        } else {
            subTestName.textContent = "Select a test to see details";
            subTestDetailText.textContent = "-";
            subTestInstructionText.textContent = "-";
        }
    });
});