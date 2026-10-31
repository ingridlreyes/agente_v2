"""Workbook declarativo: layout estable, datasets y métricas definidos por petición."""
from datetime import date, datetime
from .renderers import ink_on, readable_brand, insert_excel_logo


def metric_result(metric,dataset):
    index = next(i for i,c in enumerate(dataset.columns) if c.key==metric.column)
    values = [r.values[index] for r in dataset.rows]
    filled = [v for v in values if v is not None]
    if metric.operation=="count":
        return len(filled)
    if metric.operation=="count_equal":
        return sum(str(v)==metric.equals for v in filled)
    if not filled:
        return ""
    if metric.operation=="sum":
        return sum(filled)
    if metric.operation=="average":
        return sum(filled)/len(filled)
    di = next(i for i,c in enumerate(dataset.columns) if c.key==metric.denominator_column)
    if any((r.values[index] is None)!=(r.values[di] is None) for r in dataset.rows):
        return ""
    denom = sum(r.values[di] for r in dataset.rows if r.values[di] is not None)
    return sum(filled)/denom if denom else ""


def flexible_excel(spec,sources,path,logo=None):
    import xlsxwriter
    from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell
    wb = xlsxwriter.Workbook(path,{"strings_to_formulas":False,"strings_to_urls":False})
    wb.set_calc_mode("auto")
    plan = spec.workbook
    main = wb.add_worksheet("Dashboard")
    main.hide_gridlines(2);main.set_column("A:A",3);main.set_column("B:M",12)
    insert_excel_logo(main,logo)
    title = wb.add_format({"font_size":24,"font_color":readable_brand(spec.theme.primary),"font_name":spec.theme.font,"bold":True})
    label = wb.add_format({"font_size":11,"font_color":"#526477","text_wrap":True,"valign":"vcenter"})
    text = wb.add_format({"font_size":11,"text_wrap":True,"font_color":"#1565C0","valign":"vcenter"})
    number = wb.add_format({"font_size":11,"num_format":"#,##0.0","font_color":"#1565C0"})
    ratio = wb.add_format({"font_size":11,"num_format":"0.0%","font_color":"#1565C0"})
    date_fmt = wb.add_format({"num_format":"dd/mm/yyyy","font_color":"#1565C0"})
    big = wb.add_format({"font_size":25,"font_color":spec.theme.primary,"num_format":"#,##0.0"})
    bigratio = wb.add_format({"font_size":25,"font_color":spec.theme.primary,"num_format":"0.0%"})
    head = wb.add_format({"bg_color":spec.theme.primary,"font_color":"#"+ink_on(spec.theme.primary),"bold":True,"text_wrap":True})
    main.merge_range("B2:M3",spec.title,title)
    main.merge_range("B4:M5",spec.decision,label)
    datasets = {d.id:d for d in plan.datasets}
    pair_ranges = {}
    def rng(dataset,key):
        col = xl_col_to_name(next(i for i,c in enumerate(dataset.columns) if c.key==key))
        return "'"+dataset.name.replace("'","''")+f"'!${col}$5:${col}${max(5,4+len(dataset.rows))}"
    for dataset in plan.datasets:
        ws = wb.add_worksheet(dataset.name)
        ws.hide_gridlines(2);ws.freeze_panes(4,1);ws.set_tab_color(spec.theme.accent)
        ws.merge_range(0,0,0,len(dataset.columns)-1,dataset.name,title)
        source_label = "; ".join(f"[{s.id}] {s.title}. {s.locator}" for s in sources if s.id in dataset.source_ids)
        ws.merge_range(1,0,1,len(dataset.columns)-1,(dataset.note+" "+source_label).strip(),label)
        ws.set_row(1,45)
        for ci,column in enumerate(dataset.columns):
            ws.write_string(3,ci,column.label,head)
            width = 16 if column.kind in ("number","ratio","date") else min(52,max(24,max([len(str(r.values[ci] or '')) for r in dataset.rows]+[len(column.label)])*.75))
            ws.set_column(ci,ci,width)
        ws.set_row(3,32)
        for ri,row in enumerate(dataset.rows,4):
            height = 28
            for ci,(value,column) in enumerate(zip(row.values,dataset.columns)):
                if value is None:
                    ws.write_blank(ri,ci,None,number if column.kind=="number" else ratio if column.kind=="ratio" else text)
                elif column.kind in ("number","ratio"):
                    ws.write_number(ri,ci,value,number if column.kind=="number" else ratio)
                elif column.kind=="date":
                    ws.write_datetime(ri,ci,datetime.combine(date.fromisoformat(str(value)),datetime.min.time()),date_fmt)
                else:
                    ws.write_string(ri,ci,str(value),text)
                    height=max(height,16*(len(str(value))//35+1))
            ws.set_row(ri,min(160,height))
        if dataset.rows:
            ws.add_table(3,0,3+len(dataset.rows),len(dataset.columns)-1,{"name":"T_"+dataset.id,"style":None,"columns":[{"header":c.label,"header_format":head} for c in dataset.columns]})
        helper_column=len(dataset.columns)+1
        for metric_index,metric in enumerate(plan.metrics):
            if metric.dataset_id!=dataset.id or metric.operation!="ratio_sums":
                continue
            ws.set_column(helper_column,helper_column,24)
            ws.write_string(3,helper_column,"Datos completos: "+metric.label,head)
            ws.set_row(3,60)
            ni=next(i for i,c in enumerate(dataset.columns) if c.key==metric.column)
            di=next(i for i,c in enumerate(dataset.columns) if c.key==metric.denominator_column)
            for ri,row in enumerate(dataset.rows,4):
                n=xl_rowcol_to_cell(ri,ni);d=xl_rowcol_to_cell(ri,di)
                cache=int(isinstance(row.values[ni],(float,int)) and isinstance(row.values[di],(float,int)))
                ws.write_formula(ri,helper_column,f'=IF(AND(ISNUMBER({n}),ISNUMBER({d})),1,0)',number,cache)
            col=xl_col_to_name(helper_column)
            pair_ranges[metric_index]="'"+dataset.name.replace("'","''")+f"'!${col}$5:${col}${max(5,4+len(dataset.rows))}"
            helper_column+=1
        ws.set_landscape();ws.fit_to_pages(1,0);ws.repeat_rows(3)
    for i,metric in enumerate(plan.metrics):
        row, col = 7+(i//3)*5,1+(i%3)*4
        main.merge_range(row,col,row+1,col+2,metric.label,label)
        dataset = datasets[metric.dataset_id]
        r = rng(dataset,metric.column)
        if metric.operation=="count":
            formula=f"=COUNTA({r})"
        elif metric.operation=="count_equal":
            main.write_string(row+3,col,metric.equals or "",label)
            criteria = xl_rowcol_to_cell(row+3,col,True,True)
            formula=f"=COUNTIFS({r},{criteria})"
        elif metric.operation in ("sum","average"):
            function="SUM" if metric.operation=="sum" else "AVERAGE"
            formula=f'=IF(COUNT({r})=0,"",{function}({r}))'
        else:
            d = rng(dataset,metric.denominator_column)
            paired=f'SUM({pair_ranges[i]})'
            formula=f'=IF(OR(COUNT({r})=0,COUNT({r})<>{paired},COUNT({d})<>{paired},SUM({d})=0),"",SUM({r})/SUM({d}))'
        main.merge_range(row+2,col,row+2,col+2,"",bigratio if metric.unit=="ratio" else big)
        main.write_formula(row+2,col,formula,bigratio if metric.unit=="ratio" else big,metric_result(metric,dataset))
    chartrow = 9+((len(plan.metrics)+2)//3)*5
    for i,chart in enumerate(plan.charts):
        dataset = datasets[chart.dataset_id]
        if not dataset.rows:
            continue
        ch = wb.add_chart({"type":chart.kind})
        ch.add_series({"categories":"="+rng(dataset,chart.category_column),"values":"="+rng(dataset,chart.value_column),"fill":{"color":spec.theme.accent},"line":{"color":spec.theme.accent}})
        ch.set_title({"name":chart.title});ch.set_legend({"none":True});ch.set_chartarea({"border":{"none":True}})
        main.insert_chart(chartrow+(i//2)*16,1+(i%2)*6,ch,{"x_scale":.85,"y_scale":.85})
    tail = chartrow+((len(plan.charts)+1)//2)*16+2
    for i,assumption in enumerate(spec.assumptions):
        main.merge_range(tail+i*2,1,tail+i*2+1,12,assumption,label)
    main.merge_range(tail+len(spec.assumptions)*2+1,1,tail+len(spec.assumptions)*2+2,12,"Edita las celdas azules para recalcular. Al agregar o eliminar filas, genera una nueva versión para actualizar todos los rangos.",label)
    main.set_landscape();main.fit_to_pages(1,0)
    wb.close()
