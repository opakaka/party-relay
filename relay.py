import asyncio
import json
import os
import random
import string

import websockets

ROOMS = {}
CONNS = {}


def gen_room_id():
    while True:
        rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if rid not in ROOMS:
            return rid


def room_list():
    out = []
    for rid, r in ROOMS.items():
        out.append({
            'id': rid,
            'name': r['name'],
            'players': 1 + len(r['clients']),
            'max': r['max_players'],
            'locked': bool(r['password']),
        })
    return out


async def safe_send(ws, obj):
    try:
        await ws.send(json.dumps(obj))
    except Exception:
        pass


async def broadcast_rooms():
    data = json.dumps({'type': 'rooms', 'rooms': room_list()})
    for ws, info in list(CONNS.items()):
        if info.get('role') == 'browser':
            await safe_send(ws, json.loads(data))


async def on_message(ws, m):
    t = m.get('type')
    info = CONNS.get(ws, {})

    if t == 'register_room':
        name = str(m.get('name', 'Room'))[:32]
        pwd = str(m.get('password', ''))
        mx = max(1, min(16, int(m.get('max_players', 4))))
        rid = gen_room_id()
        ROOMS[rid] = {'name': name, 'password': pwd, 'max_players': mx,
                      'host': ws, 'clients': {}}
        CONNS[ws] = {'role': 'host', 'room_id': rid}
        await safe_send(ws, {'type': 'registered', 'room_id': rid})
        await broadcast_rooms()

    elif t == 'unregister':
        rid = info.get('room_id')
        if rid in ROOMS:
            r = ROOMS.pop(rid)
            for c in list(r['clients']):
                await safe_send(c, {'type': 'host_closed'})
                if c in CONNS:
                    CONNS[c] = {'role': 'browser'}
            CONNS[ws] = {'role': 'browser'}
        await broadcast_rooms()

    elif t == 'list_rooms':
        await safe_send(ws, {'type': 'rooms', 'rooms': room_list()})

    elif t == 'join':
        rid = str(m.get('room_id', ''))
        r = ROOMS.get(rid)
        if not r:
            await safe_send(ws, {'type': 'join_error', 'reason': 'Room not found'})
            return
        if r['password'] and r['password'] != str(m.get('password', '')):
            await safe_send(ws, {'type': 'join_error', 'reason': 'Wrong password'})
            return
        if 1 + len(r['clients']) >= r['max_players']:
            await safe_send(ws, {'type': 'join_error', 'reason': 'Room is full'})
            return
        cname = str(m.get('client_name', 'Player'))[:24]
        r['clients'][ws] = cname
        CONNS[ws] = {'role': 'client', 'room_id': rid, 'name': cname}
        await safe_send(ws, {'type': 'joined', 'room_id': rid,
                             'players': 1 + len(r['clients'])})
        await safe_send(r['host'], {'type': 'peer_joined', 'client_name': cname,
                                    'players': 1 + len(r['clients'])})
        await broadcast_rooms()

    elif t == 'leave':
        rid = info.get('room_id')
        if rid in ROOMS:
            r = ROOMS[rid]
            if info.get('role') == 'client':
                r['clients'].pop(ws, None)
                await safe_send(r['host'], {'type': 'peer_left',
                                            'client_name': info.get('name', 'Player'),
                                            'players': len(r['clients'])})
            CONNS[ws] = {'role': 'browser'}
            await broadcast_rooms()

    elif t == 'game':
        rid = info.get('room_id')
        r = ROOMS.get(rid)
        if not r:
            return
        data = m.get('data', {})
        if info.get('role') == 'host':
            for c in list(r['clients']):
                await safe_send(c, {'type': 'game', 'data': data})
        elif info.get('role') == 'client':
            await safe_send(r['host'], {'type': 'game', 'data': data})


async def handler(ws):
    CONNS[ws] = {'role': 'browser'}
    await broadcast_rooms()
    info = CONNS[ws]
    try:
        async for raw in ws:
            try:
                m = json.loads(raw)
            except Exception:
                continue
            await on_message(ws, m)
            info = CONNS.get(ws, {})
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        info = CONNS.pop(ws, None)
        if info:
            rid = info.get('room_id')
            if rid in ROOMS:
                r = ROOMS[rid]
                if info.get('role') == 'host':
                    for c in list(r['clients']):
                        await safe_send(c, {'type': 'host_closed'})
                        if c in CONNS:
                            CONNS[c] = {'role': 'browser'}
                    del ROOMS[rid]
                elif info.get('role') == 'client':
                    r['clients'].pop(ws, None)
                    await safe_send(r['host'], {'type': 'peer_left',
                                                'client_name': info.get('name', 'Player'),
                                                'players': len(r['clients'])})
            await broadcast_rooms()


async def process_request(path, headers):
    if path == '/health':
        return (200, [('Content-Type', 'text/plain')], b'ok')
    return None


async def main():
    port = int(os.environ.get('PORT', '8765'))
    async with websockets.serve(handler, '0.0.0.0', port,
                                process_request=process_request):
        print(f'Relay listening on port {port}')
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())