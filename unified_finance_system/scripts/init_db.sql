USE unified_account_system;

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    uid INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    status VARCHAR(10) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. 资金账户表
CREATE TABLE IF NOT EXISTS accounts (
    uid INT PRIMARY KEY,
    balance DECIMAL(18, 4) DEFAULT 0.0000,
    frozen DECIMAL(18, 4) DEFAULT 0.0000,
    total_pnl DECIMAL(18, 4) DEFAULT 0.0000,
    update_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 3. 授权表
CREATE TABLE IF NOT EXISTS user_app_permissions (
    uid INT,
    app_id ENUM('iMarket', 'BacPro') NOT NULL, 
    PRIMARY KEY (uid, app_id),
    FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 4. 下注流水表 (刚才报错缺这张)
CREATE TABLE IF NOT EXISTS bets (
    bet_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    uid INT NOT NULL,
    app_id ENUM('iMarket', 'BacPro') NOT NULL,
    amount DECIMAL(18, 4) NOT NULL,
    status TINYINT DEFAULT 0, -- 0:Pending, 1:Win, 2:Loss
    bet_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    settled_at DATETIME NULL,
    INDEX idx_user_app (uid, app_id)
) ENGINE=InnoDB;
