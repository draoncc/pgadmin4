/////////////////////////////////////////////////////////////
//
// pgAdmin 4 - PostgreSQL Tools
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import { render, screen, fireEvent, act } from '@testing-library/react';
import { withTheme } from '../fake_theme';
import ConnectServerContent from '../../../pgadmin/static/js/Dialogs/ConnectServerContent';

const signInData = {
  sid: 1,
  server_label: 'Azure server',
  username: 'user@example.test',
  errmsg: 'OAuth On-Behalf-Of token request failed (HTTP 400, error=interaction_required).',
  sign_in_again: true,
};

describe('ConnectServerContent sign in again', ()=>{
  const Content = withTheme(ConnectServerContent);
  let popup, openSpy, closeModal, onOK;

  const renderContent = (data=signInData)=>render(
    <Content data={data} closeModal={closeModal} onOK={onOK} />
  );
  const clickSignIn = ()=>{
    fireEvent.click(screen.getByRole('button', {name: 'Sign in again'}));
  };
  const tick = (ms)=>act(()=>{ jest.advanceTimersByTime(ms); });

  beforeEach(()=>{
    jest.useFakeTimers();
    closeModal = jest.fn();
    onOK = jest.fn();
    popup = {closed: false, close: jest.fn(), location: {pathname: '/oauth2/authorize'}};
    openSpy = jest.spyOn(window, 'open').mockReturnValue(popup);
  });

  afterEach(()=>{
    openSpy.mockRestore();
    jest.useRealTimers();
  });

  it('asks to sign in again, and not for a password', ()=>{
    renderContent();

    expect(screen.getByRole('button', {name: 'Sign in again'})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'OK'})).not.toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(screen.getByText(/Azure server/)).toBeInTheDocument();
    expect(screen.getByText(/interaction_required/)).toBeInTheDocument();
  });

  it('renews the login in a pop-up through the same provider', ()=>{
    renderContent();
    clickSignIn();

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(openSpy.mock.calls[0][0]).toBe('/oauth2/renew');
    expect(onOK).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Sign in again'})).toBeDisabled();
  });

  it('retries the connection, with no credentials, once the login is renewed', ()=>{
    renderContent();
    clickSignIn();

    tick(1000);
    expect(onOK).not.toHaveBeenCalled();

    popup.location.pathname = '/oauth2/renewed';
    tick(1000);

    expect(popup.close).toHaveBeenCalled();
    expect(onOK).toHaveBeenCalledTimes(1);
    expect([...onOK.mock.calls[0][0].keys()]).toEqual([]);
    expect(closeModal).toHaveBeenCalled();
  });

  it('retries the connection when the pop-up is closed', ()=>{
    renderContent();
    clickSignIn();

    popup.closed = true;
    tick(1000);

    expect(onOK).toHaveBeenCalledTimes(1);
  });

  it('keeps waiting while the pop-up is at the identity provider', ()=>{
    renderContent();
    clickSignIn();

    // Reading the location of another origin throws.
    Object.defineProperty(popup, 'location', {get() {
      throw new Error('cross-origin');
    }});
    tick(3000);

    expect(onOK).not.toHaveBeenCalled();
  });

  it('says so when the browser blocks the pop-up', ()=>{
    openSpy.mockReturnValue(null);
    renderContent();
    clickSignIn();

    expect(screen.getByText(/pop-up/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Sign in again'})).not.toBeDisabled();
    expect(onOK).not.toHaveBeenCalled();
  });

  it('stops waiting when the dialog goes away', ()=>{
    const {unmount} = renderContent();
    clickSignIn();
    unmount();

    popup.closed = true;
    tick(2000);

    expect(onOK).not.toHaveBeenCalled();
  });

  it('still asks for the password of a password server', ()=>{
    renderContent({
      sid: 1, server_label: 'Plain', username: 'postgres', prompt_password: true,
    });

    expect(screen.queryByRole('button', {name: 'Sign in again'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'OK'})).toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).not.toBeNull();
  });
});
