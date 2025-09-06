TrueToHire

TrueToHire is an open-source platform that helps evaluate and ensure you get the right people.

With ready-to-go test rooms, you can:

    Test candidates in real-time.

    Watch recordings of their sessions.

    Share results with others.

Want to go further? Create your own personalized test rooms.

Have a test idea for a role? Contributions are welcome!
📂 Repository Structure

    site/ – Source code for the web platform.

    docker/ – Docker-related files, including the setup script and configuration.

⚙️ Setup
1. Clone the repository

git clone https://github.com/<your-username>/truetohire.git
cd truetohire

2. Run the setup script

cd docker
chmod +x setup.sh
./setup.sh

This script will run the required pre-setup tasks.
Currently, you’ll still need to update the nginx.conf file manually (instructions below), but future updates will automate this step.
3. Configure Nginx

    Navigate to docker/nginx.conf.

    Update as needed for your environment.

🚀 Running the Application

Once setup is complete, bring up the containers:

docker compose up -d

The application should now be available at http://localhost

.
🤝 Contributing

Contributions are welcome!
If you’d like to suggest a test idea, fix a bug, or improve setup, feel free to open a pull request or an issue.
📬 Contact

For questions, feedback, or support, please open an issue
on GitHub or reach out via email: Sheemer44@outlook.com

.
