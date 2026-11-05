from decimal import Decimal, ROUND_HALF_UP
from .geometry import geometry

def validate_exam(data, strict=True):
    if not str(data.get('name','')).strip(): raise ValueError('Cần tên bài kiểm tra.')
    n=int(data.get('n',20)); scale=float(data.get('scale',10))
    if not 0<scale<=100 or not scale<float('inf'): raise ValueError('Thang điểm phải từ trên 0 đến 100.')
    g=geometry(n,data.get('sbd_digits',6),data.get('code_digits',3),data.get('columns',2 if n<=54 else 4))
    keys=data.get('keys',{})
    if not isinstance(keys,dict) or (strict and not keys): raise ValueError('Cần ít nhất một mã đề.')
    valid={}
    for code,answers in keys.items():
        if not code.isascii() or not code.isdigit() or len(code)!=g['code_digits']: raise ValueError('Mã đề phải đủ chữ số theo mẫu, giữ số 0 đầu.')
        if not isinstance(answers,list) or len(answers)!=n or any(a not in (('A','B','C','D') if strict else ('','A','B','C','D')) for a in answers):
            raise ValueError(f'Mã đề {code}: cần đủ {n} đáp án, mỗi câu một giá trị A–D.')
        valid[code]=answers
    weights=data.get('weights') or [scale/n]*n
    if not isinstance(weights,list): raise ValueError('Điểm từng câu phải là danh sách.')
    if len(weights)!=n or any(not 0<float(w)<=scale for w in weights): raise ValueError('Điểm mỗi câu phải dương, đủ số câu.')
    if abs(sum(Decimal(str(w)) for w in weights)-Decimal(str(scale)))>Decimal('.000001'):
        raise ValueError('Tổng điểm từng câu phải bằng thang điểm.')
    code_weights=data.get('code_weights') or {}
    if not isinstance(code_weights,dict) or any(code not in keys for code in code_weights): raise ValueError('Điểm riêng theo mã đề không hợp lệ.')
    for code,values in code_weights.items():
        if not isinstance(values,list) or len(values)!=n or any(not 0<float(w)<=scale for w in values): raise ValueError(f'Mã {code}: điểm mỗi câu không hợp lệ.')
        if abs(sum(Decimal(str(w)) for w in values)-Decimal(str(scale)))>Decimal('.000001'): raise ValueError(f'Mã {code}: tổng điểm phải bằng thang điểm.')
    questions=data.get('questions',[])
    if not isinstance(questions,list) or any(not isinstance(q,dict) for q in questions): raise ValueError('Danh sách câu hỏi không hợp lệ.')
    if questions and strict:
        nums=[int(q['number']) for q in questions]
        if sorted(nums)!=list(range(1,n+1)): raise ValueError('Số câu của đề thiếu, trùng hoặc không khớp đáp án.')
        for q in questions:
            if not str(q.get('text','')).strip() or set(q.get('choices',{}))!=set('ABCD') or any(not str(v).strip() for v in q['choices'].values()):
                raise ValueError('Mỗi câu cần nội dung và đủ bốn phương án A–D.')
    if data.get('multiple_rule','zero') not in ('zero','review'): raise ValueError('Quy tắc tô nhiều không hợp lệ.')
    if data.get('status','draft') not in ('draft','ready','grading','done'): raise ValueError('Trạng thái không hợp lệ.')
    return dict(geometry=g,keys=valid,weights=[float(w) for w in weights],scale=scale,questions=questions,
                multiple_rule=data.get('multiple_rule','zero'),code_weights=code_weights)

def grade(answers,key,weights):
    if len(answers)!=len(key): raise ValueError('Số câu nhận dạng không khớp đáp án.')
    counts=dict(correct=0,wrong=0,blank=0,invalid=0); total=Decimal(0)
    details=[]
    for i,(answer,right,weight) in enumerate(zip(answers,key,weights)):
        state='blank' if answer=='' else ('invalid' if len(answer)>1 else ('correct' if answer==right else 'wrong'))
        counts[state]+=1
        if state=='correct': total+=Decimal(str(weight))
        details.append(dict(number=i+1,answer=answer,key=right,state=state,weight=weight))
    return dict(score=float(total),display=str(total.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),**counts,details=details)
