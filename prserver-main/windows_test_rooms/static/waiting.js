function countdown(seconds) {
    let timer = document.getElementById("timer");
    let countdownTime = seconds;
    
    function updateTimer() {
        let minutes = Math.floor(countdownTime / 60);
        let seconds = countdownTime % 60;
        timer.innerText = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
        
        if (countdownTime <= 0) {
            window.location.href = "{% url 'test_room' test_id %}";
        } else {
            countdownTime--;
            setTimeout(updateTimer, 1000);
        }
    }
    updateTimer();
}

window.onload = function () {
    countdown(120);  // 2 minutes
};