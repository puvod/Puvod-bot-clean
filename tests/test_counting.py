import asyncio
import os
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import discord
import pytest
import pytest_asyncio

from database import Database
from counting_store import CountingStore, init_counting, parse_number, today, rank, ZONE
from cogs.counting import Counting, LeaderboardView


@pytest.mark.parametrize('text,expected', [('1',1),(' 42 hello',42),('0003',3),('0',0),
    ('1+1',None),('-1',None),('1.0',None),('',None),('hello',None),('9'*100,None),
    ('2000000001',None),('１２',None)])
def test_numbers(text,expected):
    assert parse_number(text)==expected


def test_ranks():
    assert rank(0)=='Nováček'
    assert rank(100)=='Stovkař'
    assert rank(10001)=='Counting GOAT'


@pytest.mark.asyncio
async def test_ui_pages_and_timeout():
    rows=[{'user_id':str(i),'score':20-i} for i in range(11)]
    store=SimpleNamespace(leaderboard=AsyncMock(return_value=rows))
    view=LeaderboardView(SimpleNamespace(store=store),123,456,'weekly')
    e=await view.render()
    assert e.title.endswith('Tento týden')
    assert view.previous.disabled and not view.next_page.disabled
    view.page=1
    store.leaderboard.return_value=rows[:1]
    await view.render()
    assert not view.previous.disabled and view.next_page.disabled
    view.message=SimpleNamespace(edit=AsyncMock())
    await view.on_timeout()
    assert all(c.disabled for c in view.children)
    stranger=SimpleNamespace(user=SimpleNamespace(id=999),response=SimpleNamespace(send_message=AsyncMock()))
    assert not await view.interaction_check(stranger)
    view.stop()


@pytest.mark.asyncio
async def test_other_channels_never_query_database():
    cog=Counting(SimpleNamespace())
    cog.store=SimpleNamespace(submit=AsyncMock())
    cog.configs={1:{'counting_channel_id':2,'counting_paused':False}}
    message=SimpleNamespace(author=SimpleNamespace(bot=False),guild=SimpleNamespace(id=1),channel=SimpleNamespace(id=3))
    await cog.on_message(message)
    cog.store.submit.assert_not_awaited()


@pytest_asyncio.fixture
async def store():
    # Only point TEST_DATABASE_URL at a disposable test database.
    url=os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_DATABASE_URL to an isolated PostgreSQL database for integration tests')
    pool=await asyncpg.create_pool(url,min_size=1,max_size=5)
    async with pool.acquire() as c:
        await c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
    database=Database()
    database.pool=pool
    await database.init_db()
    s=CountingStore(pool)
    await s.configure(1,counting_channel_id=10)
    yield s
    await pool.close()


async def count(s,n,mid=None,user=20,when=None):
    return await s.submit(1,10,user,mid or n,n,when or datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_migration_idempotent_and_preserves_legacy(store):
    async with store.pool.acquire() as c:
        await c.execute('DELETE FROM counting_migrations')
        await c.execute("UPDATE guild_settings SET current_number=123 WHERE guild_id='1'")
        await c.execute("INSERT INTO counting_leaderboard (guild_id,user_id,daily_counts,lifetime_counts) VALUES ('1','20',7,51)")
        await c.execute("INSERT INTO user_brawl (guild_id,user_id,tokens,gems) VALUES ('1','20',4,80)")
        await init_counting(c)
        await init_counting(c)
        assert await c.fetchval("SELECT tokens FROM user_brawl WHERE guild_id='1'")==4
    assert (await store.settings(1))['counting_record']==123
    assert (await store.profile(1,20))['lifetime_counts']==51
    assert (await store.leaderboard(1))[0]['score']==7


@pytest.mark.asyncio
async def test_atomic_count_rewards_and_no_replay(store):
    await store.configure(1,current_number=99)
    result=await count(store,100,mid=1)
    assert result['tokens']==1
    assert (await count(store,100,mid=1))['status']=='ignored'
    await store.configure(1,current_number=99)
    assert (await count(store,100,mid=2))['tokens']==0
    async with store.pool.acquire() as c:
        assert await c.fetchval("SELECT tokens FROM user_brawl WHERE guild_id='1' AND user_id='20'")==1
    assert (await store.profile(1,20))['lifetime_counts']==2
    assert (await store.leaderboard(1))[0]['score']==2
    await store.configure(1,current_number=999)
    r=await count(store,1000,mid=3)
    assert r['gems']==80 and r['tokens']==0


@pytest.mark.asyncio
async def test_wrong_solo_cooldown_pause_and_channel(store):
    t=datetime.now(timezone.utc)
    await store.configure(1,counting_allow_solo=False)
    assert (await count(store,1,when=t))['status']=='ok'
    assert (await count(store,2,when=t))['status']=='solo'
    assert (await store.settings(1))['current_number']==1
    await store.configure(1,counting_allow_solo=True,counting_cooldown=10)
    assert (await count(store,2,mid=3,when=t+timedelta(seconds=1)))['status']=='cooldown'
    assert (await count(store,2,mid=4,when=t+timedelta(seconds=11)))['status']=='ok'
    await store.configure(1,counting_paused=True)
    assert (await count(store,3,mid=5))['status']=='ignored'
    await store.configure(1,counting_paused=False)
    r=await store.submit(1,999,21,6,3,t)
    assert r['status']=='ignored'
    assert (await count(store,88,mid=7,user=21))['reset']
    s=await store.settings(1)
    assert s['current_number']==0 and s['counting_record']==2
    await store.configure(1,reset_on_fail=0)
    await count(store,1,mid=8,user=21)
    assert not (await count(store,88,mid=9,user=22))['reset']
    assert (await store.settings(1))['current_number']==1


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_reward_failure(store):
    await store.configure(1,current_number=99)
    async with store.pool.acquire() as c:
        await c.execute('ALTER TABLE user_brawl ADD CONSTRAINT test_no_tokens CHECK (tokens=0)')
    with pytest.raises(asyncpg.CheckViolationError):
        await count(store,100,mid=1)
    assert (await store.settings(1))['current_number']==99
    assert (await store.settings(1))['counting_last_message']==0
    assert (await store.profile(1,20))['lifetime_counts']==0
    assert await store.leaderboard(1)==[]


@pytest.mark.asyncio
async def test_concurrent_duplicate_message_commits_once(store):
    results=await asyncio.gather(*(count(store,1,mid=123) for _ in range(8)))
    assert sum(r['status']=='ok' for r in results)==1
    assert (await store.profile(1,20))['lifetime_counts']==1


@pytest.mark.asyncio
async def test_calendar_boundaries_and_guild_isolation(store):
    # 22:30 UTC on a summer Sunday is already Monday in Prague.
    sunday=datetime(2026,7,5,21,30,tzinfo=timezone.utc)
    monday=datetime(2026,7,5,22,30,tzinfo=timezone.utc)
    await count(store,1,when=sunday)
    await count(store,2,when=monday)
    rows=await store.leaderboard(1,'weekly',day=monday.astimezone(ZONE).date())
    assert rows[0]['score']==1
    assert await store.leaderboard(2,'lifetime')==[]
    assert await store.claim_summary(1,today())
    assert not await store.claim_summary(1,today())
    await store.release_summary(1,today())
    assert await store.claim_summary(1,today())
