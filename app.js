// app.js (Patched to use the correct data path)

async function fetchAndRenderPicks() {
    const picksContainer = document.getElementById('picks');
    const loadingMessage = document.getElementById('loading-message');
    
    // 1. Initial State: Show loading message
    loadingMessage.style.display = 'block';
    picksContainer.innerHTML = ''; 

    try {
        // --- MODIFICATION: Updated path to include the 'data/' subdirectory ---
        const response = await fetch('data/data.json'); 
        
        if (!response.ok) {
            // Note: The error message will now show the correct path if it still fails
            throw new Error(`HTTP error! Status: ${response.status} for data/data.json`);
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
            
            el.innerHTML = `
                <h3>#${pick.rank}: ${pick.team} (${pick.market})</h3>
                <p><strong>Match:</strong> ${pick.match}</p>
                <p><strong>Price:</strong> <span style="font-weight: bold; color: green;">${pick.price}</span></p>
                <p><strong>EV:</strong> <span style="font-weight: bold;">${pick.ev}</span></p>
                
                <hr style="border: 0; border-top: 1px dashed #e0e0e0; margin: 15px 0;">
                
                <div class="explanation-box" style="padding: 10px; background: #f8f8ff; border-left: 4px solid #0056b3; border-radius: 4px;">
                    <strong style="color: #0056b3; display: block; margin-bottom: 5px;">Model Explanation:</strong>
                    <p style="margin: 0; font-size: 0.95em;">${pick.reason}</p>
                </div>
            `;
            
            picksContainer.appendChild(el);
        });

    } catch (error) {
        console.error('Failed to load picks:', error);
        loadingMessage.style.display = 'none'; 
        picksContainer.innerHTML = `
            <div class="error-message" style="color: red; padding: 20px; border: 1px solid red; border-radius: 5px;">
                <h4>⚠️ Data Load Error</h4>
                <p>Could not retrieve today's picks. Please check the network connection or API status.</p>
                <p>Technical details: ${error.message}</p>
            </div>
        `;
    }
}

fetchAndRenderPicks();
