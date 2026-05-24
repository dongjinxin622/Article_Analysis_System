
CREATE TABLE domain_configs (
	id SERIAL NOT NULL, 
	domain_name VARCHAR(100) NOT NULL, 
	description TEXT, 
	entity_types JSON, 
	relation_types JSON, 
	prompt_templates JSON, 
	is_active BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
)

;


CREATE TABLE failed_logs (
	id SERIAL NOT NULL, 
	log_id VARCHAR(255) NOT NULL, 
	result_id VARCHAR(255), 
	file_name VARCHAR(500), 
	error_type VARCHAR(100), 
	error_message TEXT, 
	error_stack TEXT, 
	retry_count INTEGER, 
	status VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (log_id)
)

;


CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	nickname VARCHAR(64), 
	email VARCHAR(255), 
	avatar_url VARCHAR(512), 
	password_hash VARCHAR(255) NOT NULL, 
	is_superuser BOOLEAN, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	public_id VARCHAR(36) NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	disabled_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
)

;


CREATE TABLE batch_tasks (
	id SERIAL NOT NULL, 
	task_id VARCHAR(255) NOT NULL, 
	task_name VARCHAR(255), 
	task_type VARCHAR(50), 
	result_ids JSON, 
	config JSON, 
	enable_hitl INTEGER, 
	status VARCHAR(50), 
	total_count INTEGER, 
	processed_count INTEGER, 
	success_count INTEGER, 
	failed_count INTEGER, 
	progress FLOAT, 
	current_step VARCHAR(100), 
	error_message TEXT, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE comprehensive_tasks (
	id SERIAL NOT NULL, 
	task_id VARCHAR(255) NOT NULL, 
	user_id INTEGER NOT NULL, 
	status VARCHAR(50), 
	progress INTEGER, 
	current_step VARCHAR(100), 
	message TEXT, 
	result JSON, 
	error TEXT, 
	params JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE excel_extraction_tasks (
	id SERIAL NOT NULL, 
	task_id VARCHAR(64) NOT NULL, 
	task_name VARCHAR(255), 
	user_id INTEGER, 
	session_id VARCHAR(64), 
	original_filenames JSON, 
	strategy_file_path VARCHAR(500), 
	status VARCHAR(50), 
	total_rows INTEGER, 
	processed_rows INTEGER, 
	success_rows INTEGER, 
	failed_rows INTEGER, 
	progress FLOAT, 
	current_step VARCHAR(100), 
	error_message TEXT, 
	config JSON, 
	workflow_state JSON, 
	current_node VARCHAR(100), 
	pending_check VARCHAR(50), 
	chat_history JSON, 
	hitl_turns INTEGER, 
	output_file_path VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE processing_results (
	id SERIAL NOT NULL, 
	result_id VARCHAR(255) NOT NULL, 
	file_name VARCHAR(500) NOT NULL, 
	file_path VARCHAR(1000), 
	title VARCHAR(1000), 
	doi VARCHAR(255), 
	abstract TEXT, 
	status VARCHAR(50), 
	error_message TEXT, 
	result_pkl_path VARCHAR(1000), 
	result_json_path VARCHAR(1000), 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	processed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE prompt_templates (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	content TEXT NOT NULL, 
	description VARCHAR(500), 
	category VARCHAR(50) NOT NULL, 
	domain VARCHAR(100), 
	is_active BOOLEAN, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uix_prompt_name_user UNIQUE (name, user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE excel_extraction_rows (
	id SERIAL NOT NULL, 
	task_id VARCHAR(64), 
	row_index INTEGER, 
	raw_data JSON, 
	unique_key VARCHAR(255), 
	quality_score FLOAT, 
	quality_issues JSON, 
	status VARCHAR(50), 
	extraction_result JSON, 
	error_message TEXT, 
	retry_count INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES excel_extraction_tasks (task_id) ON DELETE CASCADE
)

;


CREATE TABLE excel_extraction_sessions (
	id SERIAL NOT NULL, 
	session_id VARCHAR(64) NOT NULL, 
	task_id VARCHAR(64), 
	is_connected BOOLEAN, 
	last_ping TIMESTAMP WITHOUT TIME ZONE, 
	hitl_pending BOOLEAN, 
	hitl_request JSON, 
	hitl_response JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES excel_extraction_tasks (task_id)
)

;


CREATE TABLE hitl_checkpoints (
	id SERIAL NOT NULL, 
	checkpoint_id VARCHAR(255) NOT NULL, 
	task_id VARCHAR(255), 
	step_name VARCHAR(100), 
	checkpoint_data JSON, 
	requires_review INTEGER, 
	reviewed INTEGER, 
	review_result VARCHAR(50), 
	review_comment TEXT, 
	reviewer_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	reviewed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES batch_tasks (task_id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
)

;


CREATE TABLE ner_results (
	id SERIAL NOT NULL, 
	ner_id VARCHAR(255) NOT NULL, 
	result_id VARCHAR(255) NOT NULL, 
	ner_json_path VARCHAR(1000), 
	ner_excel_path VARCHAR(1000), 
	ner_pkl_path VARCHAR(1000), 
	entity_count INTEGER, 
	entity_types JSON, 
	status VARCHAR(50), 
	error_message TEXT, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	processed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(result_id) REFERENCES processing_results (result_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE papers (
	id SERIAL NOT NULL, 
	paper_id VARCHAR(255) NOT NULL, 
	result_id VARCHAR(255), 
	title VARCHAR(1000), 
	doi VARCHAR(255), 
	abstract TEXT, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(result_id) REFERENCES processing_results (result_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE task_logs (
	id SERIAL NOT NULL, 
	task_id VARCHAR(255), 
	step_name VARCHAR(100), 
	action VARCHAR(50), 
	message TEXT, 
	data JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES batch_tasks (task_id) ON DELETE CASCADE
)

;


CREATE TABLE entities (
	id SERIAL NOT NULL, 
	entity_id VARCHAR(255) NOT NULL, 
	ner_id VARCHAR(255), 
	entity_type VARCHAR(100), 
	entity_name VARCHAR(500), 
	entity_text TEXT, 
	section_idx INTEGER, 
	group_idx INTEGER, 
	sentence_idx INTEGER, 
	confidence INTEGER, 
	source_sentence TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ner_id) REFERENCES ner_results (ner_id) ON DELETE CASCADE
)

;


CREATE TABLE exp_schemes (
	id SERIAL NOT NULL, 
	scheme_id VARCHAR(255) NOT NULL, 
	paper_id VARCHAR(255), 
	ner_id VARCHAR(255), 
	scheme_text TEXT, 
	dimensions JSON, 
	domain VARCHAR(50), 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(paper_id) REFERENCES processing_results (result_id), 
	FOREIGN KEY(ner_id) REFERENCES ner_results (ner_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE re_results (
	id SERIAL NOT NULL, 
	re_id VARCHAR(255) NOT NULL, 
	result_id VARCHAR(255), 
	ner_id VARCHAR(255) NOT NULL, 
	re_json_path VARCHAR(1000), 
	re_excel_path VARCHAR(1000), 
	re_pkl_path VARCHAR(1000), 
	relation_count INTEGER, 
	relation_types JSON, 
	status VARCHAR(50), 
	error_message TEXT, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	processed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(result_id) REFERENCES processing_results (result_id) ON DELETE CASCADE, 
	FOREIGN KEY(ner_id) REFERENCES ner_results (ner_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE tech_routes (
	id SERIAL NOT NULL, 
	profile_id VARCHAR(255) NOT NULL, 
	paper_id VARCHAR(255), 
	ner_id VARCHAR(255), 
	profile_text TEXT, 
	domain VARCHAR(50), 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(paper_id) REFERENCES processing_results (result_id), 
	FOREIGN KEY(ner_id) REFERENCES ner_results (ner_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;


CREATE TABLE relations (
	id SERIAL NOT NULL, 
	relation_id VARCHAR(255) NOT NULL, 
	re_id VARCHAR(255), 
	relation_type VARCHAR(100), 
	source_type VARCHAR(100), 
	source_entity VARCHAR(500), 
	target_type VARCHAR(100), 
	target_entity VARCHAR(500), 
	effect VARCHAR(50), 
	supporting_sentence TEXT, 
	confidence INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(re_id) REFERENCES re_results (re_id) ON DELETE CASCADE
)

;

CREATE UNIQUE INDEX ix_domain_configs_domain_name ON domain_configs (domain_name);
CREATE UNIQUE INDEX ix_users_public_id ON users (public_id);
CREATE INDEX ix_users_disabled_at ON users (disabled_at);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_sort_order ON users (sort_order);
CREATE UNIQUE INDEX ix_batch_tasks_task_id ON batch_tasks (task_id);
CREATE INDEX ix_comprehensive_tasks_user_id ON comprehensive_tasks (user_id);
CREATE UNIQUE INDEX ix_comprehensive_tasks_task_id ON comprehensive_tasks (task_id);
CREATE INDEX ix_excel_extraction_tasks_session_id ON excel_extraction_tasks (session_id);
CREATE UNIQUE INDEX ix_excel_extraction_tasks_task_id ON excel_extraction_tasks (task_id);
CREATE UNIQUE INDEX ix_processing_results_result_id ON processing_results (result_id);
CREATE INDEX ix_processing_results_doi ON processing_results (doi);
CREATE INDEX ix_prompt_templates_name ON prompt_templates (name);
CREATE INDEX ix_prompt_templates_user_id ON prompt_templates (user_id);
CREATE INDEX ix_excel_extraction_rows_unique_key ON excel_extraction_rows (unique_key);
CREATE UNIQUE INDEX ix_excel_extraction_sessions_session_id ON excel_extraction_sessions (session_id);
CREATE UNIQUE INDEX ix_hitl_checkpoints_checkpoint_id ON hitl_checkpoints (checkpoint_id);
CREATE UNIQUE INDEX ix_ner_results_ner_id ON ner_results (ner_id);
CREATE UNIQUE INDEX ix_papers_paper_id ON papers (paper_id);
CREATE UNIQUE INDEX ix_entities_entity_id ON entities (entity_id);
CREATE UNIQUE INDEX ix_exp_schemes_scheme_id ON exp_schemes (scheme_id);
CREATE UNIQUE INDEX ix_re_results_re_id ON re_results (re_id);
CREATE UNIQUE INDEX ix_tech_routes_profile_id ON tech_routes (profile_id);
CREATE UNIQUE INDEX ix_relations_relation_id ON relations (relation_id);
