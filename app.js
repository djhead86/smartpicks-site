// IMPROVEMENT: Switched to async/await for modern, cleaner promise handling.
async function fetchAndRenderPicks() {
    const picksContainer = document.getElementById('picks');
    const loadingMessage = document.getElementById('loading-message');
    
    // 1. Initial State: Show loading message
    loadingMessage.style.display = 'block';
    picksContainer.innerHTML = ''; // Clear container just in case

    try {
        // IMPROVEMENT: Use 'await' to pause execution until fetch is complete
        const response = await fetch('data.json'); 
        
        // IMPROVEMENT: Robust HTTP status check (Java backend best practice)
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();

        // 2. Success State: Hide loading and render data
        loadingMessage.style.display = 'none';

        if (data.length === 0) {
             picksContainer.innerHTML = '<p class="info-message">No value picks found for today. Check back tomorrow!</p>';
             return;
        }

        data.forEach(pick => {
            const el = document.createElement('div');
            el.className = 'pick';
            
            // IMPROVEMENT: Use the data.rank to correctly format the H3 and team display
            el.innerHTML = `
                <h3>#${pick.rank}: ${pick.team} (${pick.market})</h3>
                <p><strong>Match:</strong> ${pick.match}</p>
                <p><strong>Price:</strong> <span style="font-weight: bold; color: green;">${pick.price}</span></p>
                <p><strong>EV:</strong> <span style="font-weight: bold;">${pick.ev}</span></p>
                <p><strong>Reason:</strong> ${pick.reason}</p>
            `;
            picksContainer.appendChild(el);
        });

    } catch (error) {
        // 3. Error State: Handle network or parsing errors gracefully
        console.error('Failed to load picks:', error);
        loadingMessage.style.display = 'none'; // Hide loading message
        picksContainer.innerHTML = `
            <div class="error-message" style="color: red; padding: 20px; border: 1px solid red; border-radius: 5px;">
                <h4>⚠️ Data Load Error</h4>
                <p>Could not retrieve today's picks. Please check the network connection or API status.</p>
                <p>Technical details: ${error.message}</p>
            </div>
        `;
    }
}

// Start the data fetching process when the script loads
fetchAndRenderPicks();
