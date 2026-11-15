-- Human-Readable SQLite Views for Slush 2026 5-Hop Graph (`slush_5hop.sqlite`)

-- 1. Full Slush 2026 Roster (Attendees + Speakers)
DROP VIEW IF EXISTS slush_roster;
CREATE VIEW slush_roster AS
SELECT DISTINCT
    e.source_id                                   AS member_id,
    e.source_name                                 AS member_name,
    e.source_type                                 AS member_type,
    e.rel_type                                    AS slush_relationship,
    COALESCE(e.role, CASE WHEN e.rel_type = 'SPOKE_AT' THEN 'SPEAKER' ELSE 'ATTENDEE' END) AS slush_role,
    COALESCE(f.status, 'pending')                 AS hydration_status
FROM edges_raw e
LEFT JOIN frontier f ON f.entity_id = e.source_id
WHERE e.target_id = 'bc844d56-6ab4-452b-96bf-2661e86e592b'
  AND e.rel_type IN ('PARTICIPATES_IN_EVENT', 'SPOKE_AT')
ORDER BY slush_relationship DESC, member_name ASC;

-- 2. Hydrated Company Profiles (Flattened JSON properties)
DROP VIEW IF EXISTS company_profiles;
CREATE VIEW company_profiles AS
SELECT
    er.entity_id                                                                   AS id,
    er.hop                                                                         AS hop_from_slush,
    er.name                                                                        AS company_name,
    json_extract(er.record_json, '$.properties.legal_name.value')                  AS legal_name,
    json_extract(er.record_json, '$.properties.website.value')                     AS website,
    json_extract(er.record_json, '$.properties.headquarters_address.value')        AS headquarters,
    json_extract(er.record_json, '$.properties.founding_date.value')               AS founded,
    json_extract(er.record_json, '$.properties.operational_status.value')          AS status,
    json_extract(er.record_json, '$.properties.funding_stage.value')               AS funding_stage,
    CAST(json_extract(er.record_json, '$.properties.total_funding.value') AS REAL) AS total_funding_amount,
    json_extract(er.record_json, '$.properties.total_funding_units.value')         AS funding_currency,
    CASE json_array_length(json_extract(er.record_json, '$.properties.employee_count_range.value'))
        WHEN 2 THEN json_extract(er.record_json, '$.properties.employee_count_range.value[0]')
                    || '-' ||
                    json_extract(er.record_json, '$.properties.employee_count_range.value[1]')
        WHEN 1 THEN CAST(json_extract(er.record_json, '$.properties.employee_count_range.value[0]') AS TEXT)
    END                                                                            AS employees,
    json_extract(er.record_json, '$.description')                                  AS description
FROM entities_raw er
WHERE er.entity_type IN ('Company', 'Organization');

-- 3. One-Stop Company Dossier (Funding + Industries + Founders/Execs + Lead/All Investors)
DROP VIEW IF EXISTS company_dossier;
CREATE VIEW company_dossier AS
SELECT
    c.company_name,
    c.hop_from_slush,
    c.website,
    c.headquarters,
    c.founded,
    c.funding_stage,
    CASE WHEN c.total_funding_amount IS NOT NULL
         THEN PRINTF('%,.0f %s', c.total_funding_amount, COALESCE(c.funding_currency, ''))
    END AS total_funding,
    c.employees,
    (SELECT GROUP_CONCAT(DISTINCT e.target_name)
     FROM edges_raw e
     WHERE e.source_id = c.id AND e.rel_type = 'OPERATES_IN_INDUSTRY') AS industries,
    (SELECT GROUP_CONCAT(DISTINCT e.source_name || ' (' ||
            COALESCE(e.role, REPLACE(REPLACE(e.rel_type, 'IS_', ''), '_OF', '')) || ')')
     FROM edges_raw e
     WHERE e.target_id = c.id
       AND e.source_type = 'Person'
       AND e.rel_type != 'INVESTED_IN') AS leadership_and_team,
    (SELECT GROUP_CONCAT(DISTINCT e.source_name || CASE WHEN e.is_lead = 1 THEN ' [LEAD]' ELSE '' END)
     FROM edges_raw e
     WHERE e.target_id = c.id AND e.rel_type = 'INVESTED_IN') AS investors,
    c.description
FROM company_profiles c;

-- 4. People, Speakers & Connectors View
DROP VIEW IF EXISTS people_dossier;
CREATE VIEW people_dossier AS
SELECT
    n.person_id,
    n.person_name,
    CASE WHEN sr.member_id IS NOT NULL THEN 'YES (' || sr.slush_role || ')' ELSE 'NO' END AS at_slush_2026,
    COUNT(DISTINCT CASE WHEN e.target_id != 'bc844d56-6ab4-452b-96bf-2661e86e592b' THEN e.target_id END) AS connected_orgs_count,
    GROUP_CONCAT(DISTINCT CASE
        WHEN e.target_id != 'bc844d56-6ab4-452b-96bf-2661e86e592b'
        THEN e.target_name || ' [' || COALESCE(e.role, REPLACE(REPLACE(e.rel_type, 'IS_', ''), '_OF', '')) || ']'
    END) AS affiliations_and_investments,
    json_extract(er.record_json, '$.description') AS bio
FROM (
    SELECT DISTINCT source_id AS person_id, source_name AS person_name
    FROM edges_raw
    WHERE source_type = 'Person'
) n
LEFT JOIN slush_roster sr ON sr.member_id = n.person_id
LEFT JOIN entities_raw er ON er.entity_id = n.person_id
LEFT JOIN edges_raw e ON e.source_id = n.person_id
GROUP BY n.person_id, n.person_name
ORDER BY (sr.member_id IS NOT NULL) DESC, connected_orgs_count DESC, n.person_name ASC;

-- 5. Top Warm Intros View (Human-readable ranked multi-hop paths)
DROP VIEW IF EXISTS top_warm_intros;
CREATE VIEW top_warm_intros AS
SELECT
    ROUND(path_score, 3) AS score,
    hops,
    archetype,
    source_member_name   AS member_a,
    source_member_type   AS type_a,
    target_member_name   AS member_b,
    target_member_type   AS type_b,
    shared_bridge_name   AS key_connector,
    CASE WHEN tenure_overlap = 1 THEN 'YES' ELSE 'NO' END AS overlapping_tenure,
    readable_path
FROM ranked_connections
ORDER BY path_score DESC, hops ASC;
