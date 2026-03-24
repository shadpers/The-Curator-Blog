import sys
import ass
from datetime import timedelta

def time_to_milliseconds(time_str):
    """Converte tempo no formato HH:MM:SS.mmm para milissegundos."""
    try:
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split('.')
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    except:
        raise ValueError("Formato de tempo inválido. Use HH:MM:SS.mmm")

def milliseconds_to_time(ms):
    """Converte milissegundos para formato ASS (H:MM:SS.cc)."""
    td = timedelta(milliseconds=ms)
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    centiseconds = td.microseconds // 10000
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"

def main():
    if len(sys.argv) != 2:
        print("Arraste um arquivo .ass para este script.")
        input("Pressione Enter para sair...")
        return

    input_file = sys.argv[1]
    if not input_file.endswith(('.ass', '.ssa')):
        print("O arquivo deve ter extensão .ass ou .ssa.")
        input("Pressione Enter para sair...")
        return

    # Pergunta o tempo inicial e a duração do delay
    start_time = input("Digite o tempo inicial do delay (HH:MM:SS.mmm): ")
    while True:
        delay_duration = input("Digite a duração do delay em milissegundos (ex.: 90340 para 1min30.340s): ")
        if delay_duration.strip() == "":
            print("Erro: A duração do delay não pode ser vazia.")
            continue
        try:
            delay_ms = int(delay_duration)
            if delay_ms <= 0:
                print("Erro: A duração do delay deve ser um número positivo.")
                continue
            break
        except ValueError:
            print("Erro: Insira um número válido para a duração do delay (ex.: 90340).")

    try:
        start_ms = time_to_milliseconds(start_time)
    except ValueError as e:
        print(f"Erro: {e}")
        input("Pressione Enter para sair...")
        return

    # Lê o arquivo ASS
    with open(input_file, encoding='utf-8-sig') as f:
        doc = ass.parse(f)

    # Processa as legendas
    found_start = False
    for event in doc.events:
        if isinstance(event, ass.line.Dialogue):
            # Converte event.start e event.end (timedelta) para milissegundos
            event_start_ms = int(event.start.total_seconds() * 1000)
            event_end_ms = int(event.end.total_seconds() * 1000)

            if event_start_ms >= start_ms:
                found_start = True
                # Desloca o tempo de início e fim
                event_start_ms += delay_ms
                event_end_ms += delay_ms
                event.start = timedelta(milliseconds=event_start_ms)
                event.end = timedelta(milliseconds=event_end_ms)
            elif event_start_ms < start_ms and event_end_ms >= start_ms:
                # Estende o tempo de término da legenda que cobre o start_time
                event.end = timedelta(milliseconds=start_ms + delay_ms)

    if not found_start:
        print("Nenhuma legenda encontrada após o tempo inicial especificado.")
        input("Pressione Enter para sair...")
        return

    # Salva o arquivo modificado
    output_file = input_file.rsplit('.', 1)[0] + '_ajustado.ass'
    with open(output_file, 'w', encoding='utf-8-sig') as f:
        doc.dump_file(f)

    print(f"Arquivo salvo como: {output_file}")
    input("Pressione Enter para sair...")

if __name__ == "__main__":
    main()