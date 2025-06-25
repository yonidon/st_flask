sudo apt-get install mariadb-server

nano /etc/mysql/my.cnf
add this to file : 

[mysqld]
skip-networking=0
skip-bind-address

sudo service restart mysql

sudo  mysql -u root
create database sgb;
connect sgb
CREATE USER sgb IDENTIFIED BY 'sgb';
GRANT ALL PRIVILEGES ON `sgb`.* TO `sgb`@`%` ;
mysql -usgb -psgb sgb