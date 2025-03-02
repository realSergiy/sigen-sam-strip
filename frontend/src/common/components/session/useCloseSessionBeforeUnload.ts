/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import {sessionAtom} from '@/demo/atoms';
import useSettingsContext from '@/settings/useSettingsContext';
import {useAtomValue} from 'jotai';
import {useEffect} from 'react';

/**
 * The useCloseSessionBeforeUnload sends a close session request to the REST API
 * when the window/tab is closed. It uses the keepalive flag to ensure the request
 * is sent even when the page is unloading.
 */
export default function useCloseSessionBeforeUnload() {
  const session = useAtomValue(sessionAtom);
  const {settings} = useSettingsContext();

  useEffect(() => {
    function onBeforeUpload() {
      if (session == null) {
        return;
      }

      fetch(`${settings.inferenceAPIEndpoint}/api/close_session`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        keepalive: true,
        body: JSON.stringify({
          session_id: session.id,
        }),
      });
    }
    window.addEventListener('beforeunload', onBeforeUpload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUpload);
    };
  }, [session, settings.inferenceAPIEndpoint]);
}
