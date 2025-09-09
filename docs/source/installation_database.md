Installation of PostgreSQL database
===================================



Installing local database
-------------------------

The instructions below are tested on windows. On Linux/Mac, the mindset is the same, but instructions might be slightly different.

Steps:
1. Download [PostgreSQL](https://www.postgresql.org/download/)
2. Go through the installer and install the database.
   Use a password for postgres that you can remember or store it on a safe place. You'll need it later.
3. Launch the psql program (press enter until the shell asks for the
   password configured in the installation). 
   ```
   cd \Program Files\PostgreSQL\<version>\bin
   psql -U postgres
   ```
4. Choose a user name, password and a name for the local database. In the instructions below where it says
   __myusername__, __mypassword__ and __mydbname__ you should use the names you have chosen.
   Type the following commands:
```SQL
CREATE USER myusername WITH PASSWORD 'mypasswd';
CREATE DATABASE mydbname;
GRANT ALL PRIVILEGES ON DATABASE mydbname TO myusername;
\connect mydbname
GRANT CREATE ON SCHEMA public TO myusername;
```
Notes:
* Single quotes around mypasswd are required.
* Use lower case for myusername and mydbname. Postgres will convert these identifiers to lower case. 
  You can use double quotes to avoid conversion to lower case, but then you must always use the double quotes.
  Keeping everything lower case is much easier.



Installing remote database
--------------------------

The installation has to be done by an adminstrator with the appropriate rights on the server.

NOTE: This remote database should only be used in a safe and trusted environment that cannot
be accessed directly from the internet. A database that is accessable via internet without use of
a VPN will be targeted by hackers. It's not safe.


Example installation for a linux server running ubuntu.

Install postgres:
```bash
sudo apt install postgresql
```

Set up the datasbase, in your shell swich to the postgres user and run psql, e.g.,
```bash
sudo su - postgres
psql
```

Set up a database and related users:
```SQL
CREATE USER myusername WITH PASSWORD 'mypasswd';
CREATE DATABASE "mydbname";
GRANT ALL PRIVILEGES ON DATABASE 'mydbname' TO 'myusername';
\connect mydbname
GRANT CREATE ON SCHEMA public TO 'myusername';
```
*Note: The last line is required since release 15 of Postgresql. It must be executed on the new database.*

The default install of postgress does not allow external connections. We can adjest this by typing
```bash
sudo vim /etc/postgresql/12/main/postgresql.conf
```
and adding the following line:
```
listen_addresses = '*'
```
This means the postgress process will listen to all incomming requests from any ip.
Now, let's also tell postgress that users are allowed to authenticate, change the following config file,
```bash
sudo vim /etc/postgresql/12/main/pg_hba.conf
```
and add the following line,
```
host    all     all     0.0.0.0/0               md5
```
Now restart the postgres services to apply the changes,
```bash
sudo systemctl restart postgresql.service
```
Note : also make sure port 5432 is open, e.g.:
```bash
sudo ufw allow 5432
```

