SELECT
  count(DISTINCT `mdm_employee_rk`) AS `emp_cnt_total`,
  COUNT(
    DISTINCT CASE
      WHEN structure_type_nm = 'управленческая структура' THEN mdm_employee_rk
    END
  ) AS `emp_cnt_management`,
  COUNT(
    DISTINCT CASE
      WHEN structure_type_nm = 'функциональная структура' THEN mdm_employee_rk
    END
  ) AS `emp_cnt_functional`
FROM
  (
    WITH
      warden_array AS (
        SELECT
          ad_login,
          warden_cross_data_flg,
          personal_management_unit_rk_list,
          personal_functional_unit_rk_list
        FROM
          prod_proteus.warden_access_array_cross
        WHERE
          ad_login = lower('r.kazantsev')
        LIMIT
          1
      ),
      warden_filter AS (
        SELECT
          t.*
        FROM
          prod_proteus.employee_structure_union AS t
          CROSS JOIN warden_array AS w
        WHERE
          w.warden_cross_data_flg = 1
          OR w.ad_login IN (
            SELECT DISTINCT
              ad_login
            FROM
              prod_proteus.employee_structure_union
            WHERE
              admin_flg = 1
          )
          OR (
            t.structure_type_nm = 'управленческая структура'
            AND hasAny (
              w.personal_management_unit_rk_list,
              t.mapped_management_unit_rk_list
            )
          )
          OR (
            t.structure_type_nm = 'функциональная структура'
            AND hasAny (
              w.personal_functional_unit_rk_list,
              t.functional_unit_rk_list
            )
          )
      )
    SELECT
      t.mdm_employee_rk,
      t.monday_flg,
      t.ad_login,
      t.full_nm,
      t.admin_flg,
      t.hrbp_ad_login,
      t.company_hire_dt,
      t.meeting_segment_nm,
      t.in_meeting_flg,
      t.current_ad_group_nm,
      t.prev_meeting_segment_nm,
      t.prev_ad_group_nm,
      t.meeting_change_type,
      t.meeting_change_mask,
      t.meeting_changed_last_month_flg,
      t.structure_type_nm,
      groupUniqArray (t.functional_role_rk) AS functional_role_rk,
      groupUniqArray (t.functional_role_id) AS functional_role_id,
      groupUniqArray (t.allocation_prt) AS allocation_prt,
      groupUniqArray (t.unit_rk) AS unit_rk,
      groupUniqArray (t.unit_nm) AS unit_nm,
      max(t.unit_level) AS unit_level,
      groupUniqArray (t.top_level_unit_nm) AS top_level_unit_nm,
      max(t.management_head_flg) AS management_head_flg,
      max(t.technical_head_flg) AS technical_head_flg,
      max(t.service_head_flg) AS service_head_flg,
      max(
        (
          coalesce(t.management_head_flg, 0) + coalesce(t.technical_head_flg, 0) + coalesce(t.service_head_flg, 0)
        ) > 0
      ) AS head_flg,
      groupUniqArray (t.main_monday_mdm_employee_rk) AS main_monday_mdm_employee_rk,
      max(t.main_monday_ad_login) AS main_monday_ad_login,
      t.employee_profile_url,
      groupUniqArray (t.tech_monday_mdm_employee_rk) AS tech_monday_mdm_employee_rk,
      groupUniqArray (t.tech_monday_ad_login) AS tech_monday_ad_login,
      groupUniqArray (t.service_monday_mdm_employee_rk) AS service_monday_mdm_employee_rk,
      groupUniqArray (t.service_monday_ad_login) AS service_monday_ad_login,
      max(t.monday_changed_flg) AS monday_changed_flg,
      max(t.tech_monday_changed_flg) AS tech_monday_changed_flg,
      max(t.service_monday_changed_flg) AS service_monday_changed_flg,
      max(t.management_head_ad_login) AS management_head_ad_login,
      arrayDistinct (arrayFlatten (groupArray (t.current_head_array))) AS current_head_array,
      arrayDistinct (arrayFlatten (groupArray (t.prev_head_array))) AS prev_head_array,
      lower('r.kazantsev') AS current_user_login
    FROM
      warden_filter AS t
    GROUP BY
      t.mdm_employee_rk,
      t.monday_flg,
      t.ad_login,
      t.full_nm,
      t.admin_flg,
      t.hrbp_ad_login,
      t.company_hire_dt,
      t.meeting_segment_nm,
      t.in_meeting_flg,
      t.current_ad_group_nm,
      t.prev_meeting_segment_nm,
      t.prev_ad_group_nm,
      t.meeting_change_type,
      t.meeting_change_mask,
      t.meeting_changed_last_month_flg,
      t.structure_type_nm,
      t.employee_profile_url
  ) AS `virtual_table`
WHERE
  `main_monday_ad_login` = 'v.tsyganov'
  AND `meeting_segment_nm` IN ('Четверговая онлайн')
ORDER BY
  `emp_cnt_total` DESC
LIMIT
  10000;