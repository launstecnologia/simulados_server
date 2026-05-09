CREATE DATABASE IF NOT EXISTS simulados
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE simulados;

CREATE TABLE IF NOT EXISTS materias (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(120) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dificuldades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tipos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(120) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS origens (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  titulo VARCHAR(255) NOT NULL DEFAULT '',
  ano VARCHAR(20) NOT NULL DEFAULT '',
  numero VARCHAR(40) NOT NULL DEFAULT '',
  raw_text VARCHAR(500) NOT NULL DEFAULT '',
  extras_json JSON NULL,
  unique_key VARCHAR(64) NOT NULL UNIQUE,
  KEY idx_origem_ano (ano),
  KEY idx_origem_titulo (titulo)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS topicos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tags (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(255) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS questoes (
  id VARCHAR(40) PRIMARY KEY,
  materia_id INT NULL,
  tipo_id INT NULL,
  dificuldade_id INT NULL,
  origem_id BIGINT NULL,
  gabarito VARCHAR(20) NULL,
  enunciado_html LONGTEXT NULL,
  resolucao_html LONGTEXT NULL,
  alternativas_json JSON NULL,
  textos_html_json JSON NULL,
  bncc_json JSON NULL,
  topicos_json JSON NULL,
  tags_json JSON NULL,
  source_hash VARCHAR(64) NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_q_materia (materia_id),
  KEY idx_q_tipo (tipo_id),
  KEY idx_q_dificuldade (dificuldade_id),
  KEY idx_q_origem (origem_id),
  CONSTRAINT fk_q_materia FOREIGN KEY (materia_id) REFERENCES materias(id),
  CONSTRAINT fk_q_tipo FOREIGN KEY (tipo_id) REFERENCES tipos(id),
  CONSTRAINT fk_q_dificuldade FOREIGN KEY (dificuldade_id) REFERENCES dificuldades(id),
  CONSTRAINT fk_q_origem FOREIGN KEY (origem_id) REFERENCES origens(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS questao_topicos (
  questao_id VARCHAR(40) NOT NULL,
  topico_id INT NOT NULL,
  PRIMARY KEY (questao_id, topico_id),
  CONSTRAINT fk_qt_questao FOREIGN KEY (questao_id) REFERENCES questoes(id) ON DELETE CASCADE,
  CONSTRAINT fk_qt_topico FOREIGN KEY (topico_id) REFERENCES topicos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS questao_tags (
  questao_id VARCHAR(40) NOT NULL,
  tag_id INT NOT NULL,
  PRIMARY KEY (questao_id, tag_id),
  CONSTRAINT fk_qtag_questao FOREIGN KEY (questao_id) REFERENCES questoes(id) ON DELETE CASCADE,
  CONSTRAINT fk_qtag_tag FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sync_status (
  id INT PRIMARY KEY,
  last_run_at TIMESTAMP NULL,
  total_questoes INT NOT NULL DEFAULT 0,
  inserted_count INT NOT NULL DEFAULT 0,
  updated_count INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

INSERT INTO sync_status (id) VALUES (1)
ON DUPLICATE KEY UPDATE id = VALUES(id);
